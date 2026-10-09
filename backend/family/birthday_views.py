from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from .birthdays import can_plan, local_now, next_occurrence, plan_query, project, targets
from .models import BirthdayGiftPlan, BirthdayPerson, Family, Membership, ShoppingItem, ShoppingList, Task, TaskList
from .views import family_ids


def requested_family(request):
    value = request.query_params.get("family") or request.data.get("family")
    try:
        family = Family.objects.filter(pk=value,status="active",memberships__user=request.user).first()
    except (ValueError, DjangoValidationError):
        family = None
    if not family:
        raise NotFound("Family not found.")
    return family


class BirthdayPersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = BirthdayPerson
        fields = ["id","family","name","birth_month","birth_day","birth_year","relation","notes","active","created_at"]
        read_only_fields = ["created_at"]

    def validate(self,attrs):
        instance = self.instance
        family = attrs.get("family") or instance.family
        request = self.context["request"]
        if instance and family.id!=instance.family_id:
            raise ValidationError({"family":"Birthday cannot move between families."})
        if not Membership.objects.filter(family=family,user=request.user,role__in=["owner","adult"]).exists():
            raise PermissionDenied("Only owners/adults can manage external birthdays.")
        month = attrs.get("birth_month",getattr(instance,"birth_month",None))
        day = attrs.get("birth_day",getattr(instance,"birth_day",None))
        year = attrs.get("birth_year",getattr(instance,"birth_year",None))
        try:
            born = date(year or 2000,month,day)
            if year and (year<1900 or born>local_now(family).date()):
                raise ValueError()
        except (TypeError,ValueError):
            raise ValidationError({"birth_day":"Invalid birthday date."})
        return attrs

    def to_representation(self,instance):
        data = super().to_representation(instance)
        if not Membership.objects.filter(family=instance.family,user=self.context['request'].user,role__in=["owner","adult"]).exists():
            data.pop("notes",None)
        return data


class BirthdayPersonViewSet(viewsets.ModelViewSet):
    serializer_class = BirthdayPersonSerializer

    def get_queryset(self):
        return BirthdayPerson.objects.filter(family_id__in=family_ids(self.request.user),family__status="active").order_by("name", "id")

    def perform_create(self,serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self,instance):
        if not Membership.objects.filter(family=instance.family,user=self.request.user,role__in=["owner","adult"]).exists():
            raise PermissionDenied()
        instance.active=False
        instance.save(update_fields=["active","updated_at"])


@api_view(["GET"])
def birthday_list(request):
    family=requested_family(request)
    return Response({"birthdays":project(family,request.user),"leap_day_policy":"february_28","can_manage":Membership.objects.filter(family=family,user=request.user,role__in=["owner","adult"]).exists()})


@api_view(["POST"])
@transaction.atomic
def gift_plan(request):
    family=requested_family(request)
    Family.objects.select_for_update().get(pk=family.pk)
    target=next((x for x in targets(family,request.user) if x['key']==request.data.get('birthday_key')),None)
    if not target:
        raise NotFound("Birthday not found.")
    if not can_plan(family,request.user,target):
        raise PermissionDenied("Gift plans are private to the other family members.")
    today=local_now(family).date()
    upcoming=next_occurrence(target['birth_month'],target['birth_day'],today)
    status=request.data.get('status')
    if status is not None and status not in {'none','idea','planned','ordered','ready','given'}:
        raise ValidationError({'status':'Invalid gift status.'})
    idea=request.data.get('idea_text')
    if idea is not None and (not isinstance(idea,str) or len(idea)>4000):
        raise ValidationError({'idea_text':'Use at most 4000 characters.'})
    action=request.data.get('action')
    if action not in {None,'task','shopping'}:
        raise ValidationError({'action':'Invalid action.'})
    task_list=shopping_list=None
    if action=='task':
        task_list=TaskList.objects.filter(family=family,archived=False,pk=request.data.get('list_id')).first() if request.data.get('list_id') else TaskList.objects.filter(family=family,archived=False).first()
        if request.data.get('list_id') and not task_list:
            raise ValidationError({'list_id':'List belongs to another family.'})
    if action=='shopping':
        shopping_list=ShoppingList.objects.filter(family=family,archived=False,pk=request.data.get('list_id')).first() if request.data.get('list_id') else ShoppingList.objects.filter(family=family,archived=False).first()
        if request.data.get('list_id') and not shopping_list:
            raise ValidationError({'list_id':'List belongs to another family.'})
    plan,_=BirthdayGiftPlan.objects.get_or_create(family=family,occurrence_year=upcoming.year,**plan_query(target))
    if status is not None:plan.status=status
    if idea is not None:
        plan.idea_text=idea
        if plan.status=='none' and idea.strip():plan.status='idea'
    english=family.locale.startswith('en')
    if action=='task' and not plan.linked_task_id:
        task_list=task_list or TaskList.objects.get_or_create(family=family,name='Geschenke' if not english else 'Gifts')[0]
        due=max(today+timedelta(days=1),upcoming-timedelta(days=7))
        plan.linked_task=Task.objects.create(family=family,task_list=task_list,title=f"Get a gift for {target['name']}" if english else f"Geschenk für {target['name']} besorgen",due_at=datetime.combine(due,time(18),ZoneInfo(family.timezone)),created_by=request.user,source=f'birthday:{plan.id}',birthday_context=plan.id,hidden_from_user_id=target['target_user'],tags=['birthday'])
        plan.status='planned'
    if action=='shopping' and not plan.linked_shopping_item_id:
        shopping_list=shopping_list or ShoppingList.objects.create(family=family,name='Gifts' if english else 'Geschenke')
        plan.linked_shopping_item=ShoppingItem.objects.create(shopping_list=shopping_list,name=plan.idea_text.strip()[:160] or (f"Gift for {target['name']}" if english else f"Geschenk für {target['name']}"),added_by=request.user,birthday_context=plan.id,hidden_from_user_id=target['target_user'])
        if plan.status in {'none','idea'}:plan.status='planned'
    plan.save()
    return Response(next(x for x in project(family,request.user,today) if x['key']==target['key']))
