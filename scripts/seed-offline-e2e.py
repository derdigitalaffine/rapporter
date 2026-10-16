"""Disposable CI database only. No production endpoint or fixture backdoor."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
if not settings.DEBUG or os.environ.get('OFFLINE_E2E') != '1':
    raise RuntimeError('Offline integration seed requires DEBUG and OFFLINE_E2E=1')
from django.contrib.auth import get_user_model
from family.models import Family,Membership,ShoppingList,ShoppingItem,TaskList,Task,FamilyEvent,IntegrationSource
from django.utils import timezone
user,_=get_user_model().objects.get_or_create(username='offline-e2e')
user.set_password('offline-e2e-only-password');user.save()
family,_=Family.objects.get_or_create(slug='offline-e2e',defaults={'name':'Offline Test Family'})
Membership.objects.get_or_create(user=user,family=family,defaults={'role':'owner','display_name':'Offline Owner'})
shopping,_=ShoppingList.objects.get_or_create(family=family,name='Offline Shopping')
ShoppingItem.objects.get_or_create(shopping_list=shopping,name='Offline milk')
tasks,_=TaskList.objects.get_or_create(family=family,name='Offline Tasks')
Task.objects.get_or_create(family=family,task_list=tasks,title='Offline task',defaults={'created_by':user})
FamilyEvent.objects.get_or_create(family=family,type='calendar.event',title='Offline appointment',defaults={'starts_at':timezone.now(),'ends_at':timezone.now()+timezone.timedelta(hours=1)})
source,_=IntegrationSource.objects.get_or_create(family=family,name='Read-only ICS',kind='ics')
FamilyEvent.objects.get_or_create(family=family,source=source,type='calendar.event',title='Read-only external',defaults={'starts_at':timezone.now(),'ends_at':timezone.now()+timezone.timedelta(hours=1)})
print('Offline integration fixtures ready')

# Historical child membership: deliberately no BabyProfile or Guardian backfill.
child_user,_=get_user_model().objects.get_or_create(username='offline-e2e-child')
Membership.objects.get_or_create(user=child_user,family=family,defaults={'role':'child','display_name':'Offline Child'})
