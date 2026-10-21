from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import (
    AdminUserCreationForm,
    UserChangeForm,
)
from django.contrib.auth.models import User

from api.services.accounts import apply_login_email

from .models import Category, Learner, UserWord, Word, WordCategory


class FlagStatusFilter(admin.SimpleListFilter):
    title = "flag status"
    parameter_name = "flag_status"

    def lookups(self, request, model_admin):
        return (
            ("flagged", "Flagged"),
            ("unflagged", "Unflagged"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "flagged":
            return queryset.filter(flagged_by__isnull=False)
        if value == "unflagged":
            return queryset.filter(flagged_by__isnull=True)
        return queryset


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
admin.site.index_template = "admin/juzi_index.html"


@admin.register(Learner)
class LearnerAdmin(admin.ModelAdmin):
    list_display = ("user", "proficiency_level")
    list_select_related = ("user",)
    list_filter = ("proficiency_level",)
    autocomplete_fields = ("user",)
    search_fields = ("user__username", "user__email")


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("chinese", "pinyin", "english_basic", "hsk_level", "flagged_by")
    list_display_links = ("chinese",)
    list_filter = (FlagStatusFilter, "flagged_by")
    list_select_related = ("flagged_by",)
    search_fields = ("chinese", "simplified", "pinyin", "english_basic")
    readonly_fields = ("reporter",)
    fieldsets = (
        (
            "Vocabulary",
            {
                "fields": (
                    "chinese",
                    "simplified",
                    "pinyin",
                    "english_basic",
                    "hsk_level",
                ),
            },
        ),
        (
            "Example",
            {
                "fields": (
                    "example_sentence_traditional",
                    "example_sentence_simplified",
                    "example_sentence_pinyin",
                    "example_sentence_english",
                ),
            },
        ),
        (
            "Review",
            {
                "fields": ("reporter",),
            },
        ),
    )

    @admin.display(description="Reporter")
    def reporter(self, obj: Word) -> str:
        if obj.flagged_by_id is None:
            return "—"
        return str(obj.flagged_by)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id is not None:
            word = self.get_object(request, object_id)
            extra_context["show_save_and_unflag"] = bool(
                word is not None and word.flagged_by_id is not None
            )
        else:
            extra_context["show_save_and_unflag"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        if change and "_save_and_unflag" in request.POST:
            obj.flagged_by = None
        super().save_model(request, obj, form, change)

    def construct_change_message(self, request, form, formsets, add=False):
        change_message = super().construct_change_message(request, form, formsets, add)
        if not add and "_save_and_unflag" in request.POST:
            change_message = list(change_message)
            change_message.append({"changed": {"fields": ["flagged_by"]}})
        return change_message

    def response_change(self, request, obj):
        if "_save_and_unflag" in request.POST:
            self.message_user(request, "Saved and unflagged.", messages.SUCCESS)
        return super().response_change(request, obj)


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
