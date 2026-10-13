from django.urls import path
from . import family_views, views

urlpatterns = [
    path("account/", views.account), path("contacts/", views.contacts),
    path("family-contacts/", family_views.family_contacts), path("family-conversations/", family_views.family_conversation),
    path("contacts/<uuid:friendship_id>/", views.contact_action), path("blocks/<int:user_id>/", views.unblock),
    path("invitations/", views.invitations), path("invitations/<uuid:invitation_id>/", views.invitation_action),
    path("invite/preview/", views.invitation_preview), path("invite/accept/", views.invitation_accept), path("invite/register/", views.invitation_register),
    path("conversations/", views.conversations), path("conversations/<uuid:conversation_id>/", views.conversation_detail),
    path("conversations/<uuid:conversation_id>/messages/", views.messages), path("conversations/<uuid:conversation_id>/messages/<uuid:message_id>/", views.message_detail),
    path("conversations/<uuid:conversation_id>/typing/", views.typing), path("conversations/<uuid:conversation_id>/read/", views.read),
    path("attachments/<uuid:attachment_id>/", views.attachment), path("avatars/<int:user_id>/", views.avatar),
]
