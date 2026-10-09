from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, Membership, Routine, RoutineLog, ShoppingItem, ShoppingList
from .models_features import ShoppingPurchaseEvent
from .predictions import routine_prediction


class PredictionTests(TestCase):
    def setUp(self):
        User=get_user_model();self.user=User.objects.create_user('predict-owner',password='pw');self.family=Family.objects.create(name='Predict',slug='predict');self.membership=Membership.objects.create(family=self.family,user=self.user,role=Membership.Role.OWNER);self.shopping=ShoppingList.objects.create(family=self.family,name='Einkauf');self.client=APIClient();self.client.force_authenticate(self.user)
    def _purchase(self,name,days_ago):
        at=timezone.now()-timedelta(days=days_ago);ShoppingItem.objects.create(shopping_list=self.shopping,name=name,checked=True,checked_at=at,added_by=self.user)
    def test_repeated_shopping_and_routine_history_produce_explainable_suggestions(self):
        for days in [21,14,7]:self._purchase('Milch',days)
        routine=Routine.objects.create(family=self.family,name='Bettwäsche wechseln')
        for days in [21,14,7]:RoutineLog.objects.create(routine=routine,done_at=timezone.now()-timedelta(days=days),done_by=self.user)
        self.assertEqual(ShoppingPurchaseEvent.objects.filter(family=self.family,normalized_name='milch').count(),3)
        response=self.client.get(f'/api/predictions/?family={self.family.id}');self.assertEqual(response.status_code,200);suggestions=response.data['suggestions'];self.assertEqual({row['kind'] for row in suggestions},{'shopping','routine'});milk=next(row for row in suggestions if row['kind']=='shopping');self.assertEqual(milk['sample_count'],3);self.assertAlmostEqual(milk['interval_days'],7,places=1);self.assertGreaterEqual(milk['confidence'],.55)
    def test_routine_cold_start_and_irregular_history_do_not_fake_precision(self):
        routine=Routine.objects.create(family=self.family,name='Filter reinigen');RoutineLog.objects.create(routine=routine,done_at=timezone.now()-timedelta(days=2),done_by=self.user);self.assertEqual(routine_prediction(routine)['status'],'not_enough_data')
        for days in [16,14,1]:RoutineLog.objects.create(routine=routine,done_at=timezone.now()-timedelta(days=days),done_by=self.user)
        prediction=routine_prediction(routine);self.assertLess(prediction['confidence'],.75);self.assertIn(prediction['status'],{'learning','upcoming','due','overdue'})
    def test_open_item_and_feedback_suppress_without_automatic_action(self):
        for days in [21,14,7]:self._purchase('Kaffee',days)
        ShoppingItem.objects.create(shopping_list=self.shopping,name='Kaffee',checked=False,added_by=self.user)
        self.assertEqual(self.client.get(f'/api/predictions/?family={self.family.id}').data['suggestions'],[])
        ShoppingItem.objects.filter(shopping_list=self.shopping,name='Kaffee',checked=False).delete()
        suggestion=self.client.get(f'/api/predictions/?family={self.family.id}').data['suggestions'][0]
        feedback=self.client.post('/api/predictions/feedback/',{'family':str(self.family.id),'kind':'shopping','subject_key':suggestion['subject_key'],'action':'dismiss'},format='json');self.assertEqual(feedback.status_code,200);self.assertEqual(self.client.get(f'/api/predictions/?family={self.family.id}').data['suggestions'],[])
        self.assertFalse(ShoppingItem.objects.filter(shopping_list=self.shopping,name='Kaffee',checked=False).exists())
    def test_prediction_api_is_tenant_scoped(self):
        other=Family.objects.create(name='Other',slug='predict-other');response=self.client.get(f'/api/predictions/?family={other.id}');self.assertEqual(response.status_code,403)
