"""Sign in with the username in any capital letters (riswan, Riswan, RISWAN are the same person)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        users = list(User._default_manager.filter(**{User.USERNAME_FIELD + "__iexact": username.strip()})[:2])
        if len(users) != 1:                        # nobody, or two accounts that differ only in capitals: ask for the exact name
            return super().authenticate(request, username=username, password=password, **kwargs)
        user = users[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        User().set_password(password)              # same time whether or not the name exists
        return None
