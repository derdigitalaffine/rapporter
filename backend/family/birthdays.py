"""One canonical birthday projection for API, calendar, Home and scheduler.

Leap-day policy: celebrate on February 28 in non-leap years.
Birthday dates always use the family's local calendar, never UTC dates.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .models import BirthdayGiftPlan, BirthdayPerson, BirthdayReminder, Family, Membership
from .models_features import NotificationPreference
from .push import send_user_push


def local_now(family, now=None):
    return (now or timezone.now()).astimezone(ZoneInfo(family.timezone))


def occurrence(month, day, year):
    try:
        return date(year, month, day)
    except ValueError:
        if month==2 and day==29:
            return date(year, 2, 28)
        raise


def next_occurrence(month, day, today):
    result = occurrence(month, day, today.year)
    return occurrence(month, day, today.year+1) if result<today else result


def targets(family, user):
    result = []
    for member in family.memberships.select_related("user", "user__familyos_profile"):
        profile = getattr(member.user, "familyos_profile", None)
        if not profile or not profile.birth_month or not profile.birth_day:
            continue
        if member.birthday_visibility=="hidden" and member.user_id!=user.id:
            continue
        year = profile.birth_year if member.user_id==user.id or member.birthday_visibility=="full_date" else None
        result.append({"key":f"member:{member.id}", "id":str(member.id), "kind":"member", "name":member.display_name or member.user.username, "birth_month":profile.birth_month, "birth_day":profile.birth_day, "birth_year":year, "target_user":member.user_id, "created_at":max(member.created_at, profile.updated_at), "relation":"", "object":member})
    for person in family.birthday_people.filter(active=True):
        result.append({"key":f"person:{person.id}", "id":str(person.id), "kind":"person", "name":person.name, "birth_month":person.birth_month, "birth_day":person.birth_day, "birth_year":person.birth_year, "target_user":None, "created_at":person.created_at, "relation":person.relation, "object":person})
    return result


def can_plan(family, user, target):
    return target["target_user"]!=user.id and Membership.objects.filter(family=family, user=user, role__in=["owner", "adult", "teen"]).exists()


def plan_query(target):
    return {"membership_id":target["id"]} if target["kind"]=="member" else {"person_id":target["id"]}


def project(family, user, today=None):
    today = today or local_now(family).date()
    plans = list(BirthdayGiftPlan.objects.filter(family=family).select_related("linked_task"))
    result = []
    for target in targets(family,user):
        upcoming = next_occurrence(target["birth_month"], target["birth_day"], today)
        allowed = can_plan(family,user,target)
        plan = next((x for x in plans if x.occurrence_year==upcoming.year and (str(x.membership_id)==target["id"] if target["kind"]=="member" else str(x.person_id)==target["id"])), None) if allowed else None
        status = ("ready" if plan.linked_task and plan.linked_task.completed_at and plan.status!="given" else plan.status) if plan else "none"
        if plan and plan.linked_task and not plan.linked_task.completed_at and status=="ready":
            status = "planned"
        row = {key:target[key] for key in ["key", "id", "kind", "name", "birth_month", "birth_day", "birth_year", "relation"]}
        row.update(next_occurrence=upcoming.isoformat(),days_until=(upcoming-today).days,turning_age=upcoming.year-target["birth_year"] if target["birth_year"] else None,can_plan=allowed)
        if allowed:
            row.update(gift_status=status,idea_text=plan.idea_text if plan else "",gift_plan_id=str(plan.id) if plan else None,linked_task=str(plan.linked_task_id) if plan and plan.linked_task_id else None,linked_shopping_item=str(plan.linked_shopping_item_id) if plan and plan.linked_shopping_item_id else None,suggested_action="celebrate" if upcoming==today else "gift_ready" if status in {"ready","given"} else "gift_prepare")
        result.append(row)
    return sorted(result,key=lambda x:(x["next_occurrence"],x["name"].casefold()))


def calendar_projection(family,user,start,end):
    rows = []
    for target in targets(family,user):
        for year in range(start.year,end.year+1):
            day = occurrence(target["birth_month"],target["birth_day"],year)
            if start<=day<=end:
                start_at = datetime.combine(day,time.min,ZoneInfo(family.timezone))
                rows.append({"id":f"birthday:{target['key']}:{year}","family":str(family.id),"source":None,"type":"birthday","title":f"{target['name']}: Geburtstag" if not family.locale.startswith("en") else f"{target['name']}'s birthday","starts_at":start_at.isoformat(),"ends_at":datetime.combine(day+timedelta(days=1),time.min,ZoneInfo(family.timezone)).isoformat(),"actionable":True,"payload":{"all_day":True,"birthday_key":target["key"],"provider":"FamilyOS","url":f"/?page=birthdays&birthday={target['key']}"}})
    return rows


def run_birthday_reminders(now=None):
    count = 0
    for family in Family.objects.filter(status=Family.Status.ACTIVE):
        local = local_now(family,now)
        if local.hour<9:
            continue
        for member in family.memberships.select_related("user"):
            prefs = NotificationPreference.objects.filter(membership=member).first()
            source_targets = {x["key"]:x for x in targets(family,member.user)}
            for row in project(family,member.user,local.date()):
                stage = row["days_until"]
                if stage not in {21,7,1,0}:
                    continue
                if stage in {21,7} and (not row["can_plan"] or row.get("gift_status") in {"ready","given"}):
                    continue
                if prefs and not getattr(prefs,"birthday_prepare" if stage in {21,7} else "birthdays",True):
                    continue
                # New records never generate earlier reminder stages retroactively.
                target = source_targets[row["key"]]
                if local_now(family,target["created_at"]).date()>local.date():
                    continue
                reminder,created = BirthdayReminder.objects.get_or_create(membership=member,target_key=row["key"],occurrence_year=int(row["next_occurrence"][:4]),stage=stage)
                if not created:
                    continue
                english = family.locale.startswith("en")
                body = (f"Today is {row['name']}'s birthday!" if stage==0 else f"{row['name']}'s birthday is in {stage} day(s).") if english else (f"Heute hat {row['name']} Geburtstag!" if stage==0 else f"{row['name']} hat in {stage} Tagen Geburtstag.")
                if stage in {21,7}:
                    labels = {"none":("No gift prepared yet.","Noch kein Geschenk vorbereitet."),"idea":("A gift idea is noted.","Eine Geschenkidee ist notiert."),"planned":("The gift is being prepared.","Das Geschenk ist geplant."),"ordered":("The gift has been ordered.","Das Geschenk ist bestellt.")}
                    body += " " + labels.get(row.get("gift_status"),labels["none"])[0 if english else 1]
                # Unique claim + stable notification tag gives one scheduler delivery
                # per recipient/occurrence/stage, including concurrent scheduler runs.
                send_user_push(member.user,"Birthday" if english else "Geburtstag",body,f"/?page=birthdays&family={family.id}&birthday={row['key']}",tag=f"birthday:{family.id}:{row['key']}:{row['next_occurrence']}:{stage}")
                reminder.delivered_at=timezone.now();reminder.save(update_fields=["delivered_at","updated_at"])
                count += 1
    return count
