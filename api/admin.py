from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import (
    AdminUserCreationForm,
    UserChangeForm,
)
from django.contrib.auth.models import User

from api.services.accounts import apply_login_email

from .models import Category, Learner, UserWord, Word, WordCategory


class EmailUsernameCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].help_text = "Login email. Saved to both username and email."

    def clean_username(self):
        # Validate shape + normalize before uniqueness checks see the value.
        user = User()
        return apply_login_email(user, self.cleaned_data["username"])

    def save(self, commit=True):
        user = super().save(commit=False)
        apply_login_email(user, self.cleaned_data["username"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class EmailUsernameChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].help_text = "Login email. Saved to both username and email."

    def clean_username(self):
        user = self.instance
        return apply_login_email(user, self.cleaned_data["username"])

    def save(self, commit=True):
        user = super().save(commit=False)
        apply_login_email(user, self.cleaned_data["username"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class EmailUserAdmin(DjangoUserAdmin):
    form = EmailUsernameChangeForm
    add_form = EmailUsernameCreationForm
    list_display = ("username", "email", "is_staff", "is_active")
    search_fields = ("username", "email")
    ordering = ("username",)


admin.site.unregister(User)
admin.site.register(User, EmailUserAdmin)


@admin.register(Learner)
class LearnerAdmin(admin.ModelAdmin):
    list_display = ("user", "study_level")
    list_select_related = ("user",)
    list_filter = ("study_level",)
    autocomplete_fields = ("user",)
    search_fields = ("user__username", "user__email")


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("chinese", "simplified", "pinyin", "english_basic", "flagged_by")
    list_filter = ("flagged_by",)
    list_select_related = ("flagged_by",)
    autocomplete_fields = ("flagged_by",)
    search_fields = ("chinese", "simplified", "pinyin", "english_basic")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(WordCategory)
class WordCategoryAdmin(admin.ModelAdmin):
    list_display = ("category", "word")
    list_select_related = ("category", "word")
    autocomplete_fields = ("category", "word")


@admin.register(UserWord)
class UserWordAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "word",
        "easy_streak",
        "easy_count",
        "due_on",
        "last_practiced_at",
    )
    list_select_related = ("user", "word")
    autocomplete_fields = ("user", "word")
    search_fields = (
        "word__chinese",
        "word__pinyin",
        "word__english_basic",
        "user__username",
        "user__email",
    )
