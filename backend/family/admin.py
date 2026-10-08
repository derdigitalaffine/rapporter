from django.contrib import admin
from .models import Family, Membership, Task, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem

for model in [Family, Membership, Task, ShoppingList, ShoppingItem, Routine, RoutineLog, IntegrationSource, FamilyEvent, InboxItem]:
    admin.site.register(model)
