import io
from datetime import date,timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory,TestCase,override_settings
from django.http import HttpResponse
from PIL import Image
from rest_framework.exceptions import PermissionDenied

from family.models import Family,Membership

from .family_modules import set_care_circle,set_module
from .media_service import get_private_media_for_user,save_private_media
from .middleware import PrivateBabyNoStoreMiddleware
from .pregnancy_service import create_pregnancy


User=get_user_model()


def jpeg_with_exif():
    image=Image.new('RGB',(40,30),(120,80,40))
    exif=Image.Exif();exif[0x010E]='private pregnancy photo';exif[0x0112]=6
    stream=io.BytesIO();image.save(stream,format='JPEG',exif=exif)
    return stream.getvalue()


class BabyPrivateMediaTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user(username='media-owner',password='pw')
        self.allowed=User.objects.create_user(username='media-allowed',password='pw')
        self.denied=User.objects.create_user(username='media-denied',password='pw')
        self.family=Family.objects.create(name='Media Family',slug='media-family',locale='de',timezone='Europe/Berlin')
        self.owner_membership=Membership.objects.create(family=self.family,user=self.owner,role=Membership.Role.OWNER,display_name='Owner')
        self.allowed_membership=Membership.objects.create(family=self.family,user=self.allowed,role=Membership.Role.ADULT,display_name='Allowed')
        Membership.objects.create(family=self.family,user=self.denied,role=Membership.Role.ADULT,display_name='Denied')
        set_module(self.owner,self.family,enabled=True)
        set_care_circle(self.owner,self.family,[
            {'membership':self.owner_membership.id,'can_view_pregnancy':True,'can_log_care':True,'can_view_growth_development':True,'is_guardian':True},
            {'membership':self.allowed_membership.id,'can_view_pregnancy':True,'can_log_care':False,'can_view_growth_development':True,'is_guardian':False},
        ])
        self.pregnancy=create_pregnancy(self.owner,self.family,expected_due_date=date.today()+timedelta(days=90))

    @override_settings(MEDIA_ROOT='/tmp/familyos-test-media')
    def test_image_is_reencoded_without_exif_and_only_care_circle_can_read(self):
        upload=SimpleUploadedFile('photo.jpg',jpeg_with_exif(),content_type='image/jpeg')
        row=save_private_media(user=self.owner,family=self.family,upload=upload,scope='pregnancy',pregnancy=self.pregnancy)
        self.assertEqual(row.content_type,'image/webp')
        _,path=get_private_media_for_user(user=self.allowed,media_id=row.id)
        with Image.open(path) as image:
            self.assertFalse(image.getexif())
            self.assertEqual(image.format,'WEBP')
        with self.assertRaises(PermissionDenied):
            get_private_media_for_user(user=self.denied,media_id=row.id)
        path.unlink(missing_ok=True)

    @override_settings(MEDIA_ROOT='/tmp/familyos-test-media')
    def test_cascade_delete_removes_private_file_from_storage(self):
        upload=SimpleUploadedFile('photo.jpg',jpeg_with_exif(),content_type='image/jpeg')
        row=save_private_media(user=self.owner,family=self.family,upload=upload,scope='pregnancy',pregnancy=self.pregnancy)
        _,path=get_private_media_for_user(user=self.owner,media_id=row.id)
        self.assertTrue(path.exists())
        self.pregnancy.delete()
        self.assertFalse(path.exists())

    def test_private_api_middleware_disables_caching(self):
        middleware=PrivateBabyNoStoreMiddleware(lambda request:HttpResponse('ok'))
        response=middleware(RequestFactory().get('/api/baby/media/00000000-0000-0000-0000-000000000000/'))
        self.assertEqual(response['Cache-Control'],'private, no-store, max-age=0')
        self.assertEqual(response['Pragma'],'no-cache')
