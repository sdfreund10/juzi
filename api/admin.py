from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import (
    AdminUserCreationForm,
    UserChangeForm,
)
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import capfirst

from api.services.accounts import apply_login_email
from api.services.card_review import SUGGESTION_FIELDS, CardReviewFailed, review_card

from .models import Category, Learner, UserWord, Word, WordCategory

VERDICT_LABELS = {
    "no_clear_issue": "No clear issue",
    "issues_found": "Issues found",
    "remove": "Remove card",
    "needs_human_review": "Needs human review",
}


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


class ArchiveStatusFilter(admin.SimpleListFilter):
    """Shows active words by default, replacing the stock "All" choice with "Active"."""

    title = "archive status"
    parameter_name = "archived"

    def lookups(self, request, model_admin):
        return (("yes", "Archived"),)

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(archived_at__isnull=False)
        return queryset.active()

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": "Active",
        }
        yield {
            "selected": self.value() == "yes",
            "query_string": changelist.get_query_string({self.parameter_name: "yes"}),
            "display": "Archived",
        }


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


def card_review_context(word: Word) -> dict:
    try:
        review = review_card(word)
    except CardReviewFailed as exc:
        return {"error": str(exc)}
    return {
        "verdict": VERDICT_LABELS[review["verdict"]],
        "recommends_removal": review["verdict"] == "remove",
        "findings": review["findings"],
        "suggestions": [
            (capfirst(Word._meta.get_field(name).verbose_name), review["suggestions"][name])
            for name in SUGGESTION_FIELDS
        ],
    }


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = (
        "chinese",
        "pinyin",
        "english_basic",
        "hsk_level",
        "flagged_by",
        "flag_reason",
    )
    list_display_links = ("chinese",)
    list_filter = (ArchiveStatusFilter, FlagStatusFilter, "flagged_by")
    list_select_related = ("flagged_by",)
    search_fields = ("chinese", "simplified", "pinyin", "english_basic")
    readonly_fields = ("reporter", "reason", "archived_at")

    class Media:
        css = {"all": ("admin/css/card_review.css",)}

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
                "fields": ("reporter", "reason", "archived_at"),
            },
        ),
    )

    @admin.display(description="Reporter")
    def reporter(self, obj: Word) -> str:
        if obj.flagged_by_id is None:
            return "—"
        return str(obj.flagged_by)

    @admin.display(description="Reason")
    def reason(self, obj: Word) -> str:
        if not obj.flag_reason:
            return "—"
        return obj.get_flag_reason_display()

    def has_delete_permission(self, request, obj=None):
        return False

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if obj and self.has_change_permission(request, obj):
            query = request.GET.copy()
            query["include_analysis"] = "true"
            context["analyze_url"] = f"?{query.urlencode()}"
            if request.method == "GET" and "include_analysis" in request.GET:
                context["card_review"] = card_review_context(obj)
        return super().render_change_form(request, context, add, change, form_url, obj)

    def save_model(self, request, obj, form, change):
        if change and "_save_and_unflag" in request.POST:
            obj.flagged_by = None
            obj.flag_reason = ""
        if change and "_save_and_archive" in request.POST:
            obj.archived_at = timezone.now()
        if change and "_save_and_restore" in request.POST:
            obj.archived_at = None
        super().save_model(request, obj, form, change)

    def construct_change_message(self, request, form, formsets, add=False):
        change_message = super().construct_change_message(request, form, formsets, add)
        if add:
            return change_message
        fields = []
        if "_save_and_unflag" in request.POST:
            fields.extend(["flagged_by", "flag_reason"])
        if "_save_and_archive" in request.POST or "_save_and_restore" in request.POST:
            fields.append("archived_at")
        if fields:
            change_message = [*change_message, {"changed": {"fields": fields}}]
        return change_message

    def response_change(self, request, obj):
        if "_save_and_unflag" in request.POST:
            self.message_user(request, "Saved and unflagged.", messages.SUCCESS)
        if "_save_and_archive" in request.POST:
            self.message_user(request, "Saved and archived.", messages.SUCCESS)
        if "_save_and_restore" in request.POST:
            self.message_user(request, "Saved and restored.", messages.SUCCESS)
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
