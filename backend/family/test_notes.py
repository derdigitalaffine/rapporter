from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Family, Membership, Note

class NotesTests(TestCase):
 def setUp(self):
  User=get_user_model();self.author=User.objects.create_user(username='note-author');self.admin=User.objects.create_user(username='note-admin');self.reader=User.objects.create_user(username='note-reader');self.outside=User.objects.create_user(username='note-outside')
  self.family=Family.objects.create(name='Notes',slug='notes')
  for user,role in [(self.author,'adult'),(self.admin,'owner'),(self.reader,'child')]: Membership.objects.create(family=self.family,user=user,role=role)
  self.client=APIClient();self.client.force_authenticate(self.author);self.note=self.client.post('/api/notes/',{'family':str(self.family.id),'title':'Private','body':'secret'},format='json').data
 def share(self,user,permission='read'): return self.client.post(f"/api/notes/{self.note['id']}/sharing/",{'version':self.note['version'],'shares':[{'user':user.id,'permission':permission}]},format='json')
 def test_private_even_family_owner_and_immutable_identity(self):
  self.client.force_authenticate(self.admin);data=self.client.get('/api/notes/').data;self.assertEqual(data.get('results',data),[]);self.assertEqual(self.client.get(f"/api/notes/{self.note['id']}/").status_code,404)
  self.client.force_authenticate(self.author);other=Family.objects.create(name='Other',slug='other-notes');Membership.objects.create(family=other,user=self.author)
  self.assertEqual(self.client.patch(f"/api/notes/{self.note['id']}/",{'family':str(other.id),'version':1},format='json').status_code,400)
 def test_share_read_edit_revoke_foreign_rejection(self):
  self.assertEqual(self.share(self.outside).status_code,400);self.note=self.share(self.reader).data;self.client.force_authenticate(self.reader)
  self.assertEqual(self.client.get(f"/api/notes/{self.note['id']}/").status_code,200);self.assertEqual(self.client.patch(f"/api/notes/{self.note['id']}/",{'body':'changed','version':2},format='json').status_code,403);self.assertEqual(self.client.get(f"/api/notes/{self.note['id']}/history/").status_code,403)
  self.client.force_authenticate(self.author);self.note=self.share(self.reader,'edit').data;self.client.force_authenticate(self.reader)
  self.assertEqual(self.client.patch(f"/api/notes/{self.note['id']}/",{'body':'changed','version':3},format='json').status_code,200);self.assertEqual(self.client.delete(f"/api/notes/{self.note['id']}/").status_code,403)
  self.client.force_authenticate(self.author);self.assertEqual(self.client.post(f"/api/notes/{self.note['id']}/sharing/",{'shares':[],'version':4},format='json').status_code,200);self.client.force_authenticate(self.reader);self.assertEqual(self.client.get(f"/api/notes/{self.note['id']}/").status_code,404)
 def test_versions_history_search_and_limits(self):
  url=f"/api/notes/{self.note['id']}/";self.assertEqual(self.client.patch(url,{'body':'new','version':1},format='json').status_code,200);self.assertEqual(self.client.patch(url,{'body':'lost','version':1},format='json').status_code,409);self.assertEqual(Note.objects.get(pk=self.note['id']).body,'new')
  history=self.client.get(url+'history/').data;self.assertEqual(len(history.get('results',history)),2);self.assertEqual(self.client.patch(url,{'body':'x'*50001,'version':2},format='json').status_code,400);self.assertEqual(len(self.client.get('/api/notes/?search=new').data['results']),1)
 def test_drawing_bounds_and_text_stays_plain(self):
  url=f"/api/notes/{self.note['id']}/";valid=[{'color':'#abcdef','width':3,'points':[[0,0],[1000,1000]]}]
  self.assertEqual(self.client.patch(url,{'drawing':valid,'body':'<script>bad</script>','version':1},format='json').status_code,200)
  for invalid in [[{'color':'url(secret)','width':3,'points':[[0,0]]}],[{'color':'#abcdef','width':3,'points':[[1001,0]]}],valid*251]: self.assertEqual(self.client.patch(url,{'drawing':invalid,'version':2},format='json').status_code,400)
