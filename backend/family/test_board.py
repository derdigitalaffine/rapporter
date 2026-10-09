import io
import tempfile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient
from .models import Family, Membership, BoardPost, BoardImage
from .private_images import image_path, optimize_image

class BoardTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        override=override_settings(MEDIA_ROOT=self.media.name);override.enable();self.addCleanup(override.disable)
        User=get_user_model();self.author=User.objects.create_user('writer');self.adult=User.objects.create_user('adult');self.child=User.objects.create_user('child');self.outsider=User.objects.create_user('outside');self.guest=User.objects.create_user('guest')
        self.family=Family.objects.create(name='Home',slug='home');self.other=Family.objects.create(name='Other',slug='other')
        for user,role in [(self.author,'teen'),(self.adult,'adult'),(self.child,'child'),(self.guest,'guest')]:Membership.objects.create(family=self.family,user=user,role=role,display_name=user.username)
        Membership.objects.create(family=self.other,user=self.outsider,role='owner')
        self.client=APIClient();self.client.force_authenticate(self.author)
    def image(self):
        output=io.BytesIO();image=Image.new('RGB',(2400,1200),'red');exif=Image.Exif();exif[270]='secret';image.save(output,'JPEG',exif=exif)
        return SimpleUploadedFile('photo.jpg',output.getvalue(),content_type='image/jpeg')
    def create(self,images=False):
        payload={'family':str(self.family.id),'text':'Hello <script>alert(1)</script>'}
        if images:payload['images']=[self.image()]
        response=self.client.post('/api/board/',payload,format='multipart');self.assertEqual(response.status_code,201,response.data);return response
    def test_roles(self):
        post=self.create().data;self.assertEqual(post['author_name'],'writer');self.assertTrue(post['can_edit'])
        self.client.force_authenticate(self.child);self.assertEqual(self.client.patch(f"/api/board/{post['id']}/",{'text':'changed'},format='json').status_code,403);self.assertEqual(self.client.delete(f"/api/board/{post['id']}/").status_code,403)
        self.client.force_authenticate(self.adult);row=self.client.get('/api/board/').data['results'][0];self.assertFalse(row['can_edit']);self.assertTrue(row['can_delete']);self.assertEqual(self.client.delete(f"/api/board/{post['id']}/").status_code,204)
        self.client.force_authenticate(self.guest);self.assertEqual(self.client.post('/api/board/',{'family':str(self.family.id),'text':'no'},format='json').status_code,403)
    def test_image_private_optimized_cleanup(self):
        post=self.create(True).data;image=BoardImage.objects.get(post_id=post['id']);path=image_path(image.key)
        with Image.open(path) as decoded:self.assertEqual(decoded.format,'WEBP');self.assertLessEqual(max(decoded.size),1600);self.assertFalse(decoded.getexif())
        response=self.client.get(post['images'][0]['url']);self.assertEqual(response.status_code,200);self.assertEqual(response['Cache-Control'],'private, no-store')
        self.client.force_authenticate(self.outsider);self.assertEqual(self.client.get(post['images'][0]['url']).status_code,404);self.assertEqual(self.client.get(f"/api/board/{post['id']}/").status_code,404);self.assertEqual(self.client.get('/api/board/').data['results'],[])
        self.client.force_authenticate(self.author)
        with self.captureOnCommitCallbacks(execute=True):self.assertEqual(self.client.delete(f"/api/board/{post['id']}/").status_code,204)
        self.assertFalse(path.exists())
    def test_invalid_upload_and_empty(self):
        self.assertEqual(self.client.post('/api/board/',{'family':str(self.family.id),'text':' '},format='json').status_code,400)
        bad=SimpleUploadedFile('evil.svg',b'<svg onload="evil()"/>',content_type='image/svg+xml')
        self.assertEqual(self.client.post('/api/board/',{'family':str(self.family.id),'images':[bad]},format='multipart').status_code,400);self.assertFalse(BoardPost.objects.exists())
        with self.assertRaises(Exception):optimize_image(SimpleUploadedFile('huge.png',b'a'*(10*1024*1024+1)))
    def test_edit_tenant_and_impersonation_notification_privacy(self):
        with patch('family.board_views.notify_domain_event') as notify:
            with self.captureOnCommitCallbacks(execute=True):post=self.create().data
            self.assertNotIn('text',notify.call_args.kwargs['context'])
        url=f"/api/board/{post['id']}/";self.assertIn(self.client.patch(url,{'family':str(self.other.id)},format='json').status_code,[400,403])
        response=self.client.patch(url,{'text':'Changed','author':self.adult.id},format='json');self.assertEqual(response.status_code,200);self.assertEqual(response.data['author'],self.author.id)
    def test_suspended(self):
        post=self.create(True).data;self.family.status='suspended';self.family.save();self.assertEqual(self.client.get(post['images'][0]['url']).status_code,403)
    def test_pagination_image_removal(self):
        BoardPost.objects.bulk_create([BoardPost(family=self.family,author=self.author,text=str(i)) for i in range(25)])
        response=self.client.get('/api/board/');self.assertEqual(len(response.data['results']),20);self.assertEqual(response.data['count'],25);self.assertTrue(response.data['next'])
        post=self.create(True).data
        with self.captureOnCommitCallbacks(execute=True):self.assertEqual(self.client.delete(post['images'][0]['url']).status_code,204)
        self.assertFalse(BoardImage.objects.exists())

    def test_image_count_and_atomic_validation(self):
        response=self.client.post('/api/board/',{'family':str(self.family.id),'images':[self.image() for _ in range(5)]},format='multipart')
        self.assertEqual(response.status_code,400);self.assertFalse(BoardPost.objects.exists())
        response=self.client.post('/api/board/',{'family':str(self.family.id),'images':[self.image(),SimpleUploadedFile('bad.png',b'bad')]},format='multipart')
        self.assertEqual(response.status_code,400);self.assertFalse(BoardPost.objects.exists());self.assertFalse(BoardImage.objects.exists())
    def test_orientation_and_pixel_limit(self):
        output=io.BytesIO();exif=Image.Exif();exif[274]=6;Image.new('RGB',(200,100),'red').save(output,'JPEG',exif=exif)
        data,width,height=optimize_image(SimpleUploadedFile('orient.jpg',output.getvalue()));self.assertEqual((width,height),(100,200))
        output=io.BytesIO();Image.new('RGB',(5001,5000)).save(output,'JPEG')
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):optimize_image(SimpleUploadedFile('pixels.jpg',output.getvalue()))
    def test_family_cascade_removes_media(self):
        post=self.create(True).data;key=BoardImage.objects.get(post_id=post['id']).key
        with self.captureOnCommitCallbacks(execute=True):self.family.delete()
        self.assertFalse(image_path(key).exists())
