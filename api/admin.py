from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import (
    AdminUserCreationForm,
    UserChangeForm,
)
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

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


class ArchiveStatusFilter(admin.SimpleListFilter):
    title = "archive status"
    parameter_name = "archive_status"

    def lookups(self, request, model_admin):
        return (
            ("active", "Active"),
            ("archived", "Archived"),
            ("all", "All"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "archived":
            return queryset.filter(archived_at__isnull=False)
        if value == "all":
            return queryset
        return queryset.active()

    def choices(self, changelist):
        value = self.value()
        for lookup, title in self.lookup_choices:
            yield {
                "selected": value == lookup or (lookup == "active" and value is None),
                "query_string": changelist.get_query_string({self.parameter_name: lookup}),
                "display": title,
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


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("chinese", "pinyin", "english_basic", "hsk_level", "flagged_by")
    list_display_links = ("chinese",)
    list_filter = (ArchiveStatusFilter, FlagStatusFilter, "flagged_by")
    list_select_related = ("flagged_by",)
    search_fields = ("chinese", "simplified", "pinyin", "english_basic")
    readonly_fields = ("reporter", "archived_at")
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
        (
            "Archive",
            {
                "fields": ("archived_at",),
            },
        ),
    )

    @admin.display(description="Reporter")
    def reporter(self, obj: Word) -> str:
        if obj.flagged_by_id is None:
            return "—"
        return str(obj.flagged_by)

    def get_urls(self):
        archive_name = f"{self.opts.app_label}_{self.opts.model_name}_archive"
        restore_name = f"{self.opts.app_label}_{self.opts.model_name}_restore"
        return [
            path(
                "<path:object_id>/archive/",
                self.admin_site.admin_view(self.archive_view),
                name=archive_name,
            ),
            path(
                "<path:object_id>/restore/",
                self.admin_site.admin_view(self.restore_view),
                name=restore_name,
            ),
            *super().get_urls(),
        ]

    def has_delete_permission(self, request, obj=None):
        return False

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

    def archive_view(self, request, object_id: str) -> TemplateResponse | HttpResponseRedirect:
        word = self._word_for_change(request, object_id)
        if word.archived_at is not None:
            self.message_user(request, "Already archived.", messages.INFO)
            return HttpResponseRedirect(reverse("admin:api_word_change", args=[word.pk]))
        if request.method == "POST":
            word.archive()
            self.log_change(request, word, [{"changed": {"fields": ["archived_at"]}}])
            self.message_user(request, "Archived.", messages.SUCCESS)
            return HttpResponseRedirect(reverse("admin:api_word_changelist"))
        return self._render_confirmation(
            request,
            word,
            title="Archive word",
            breadcrumb="Archive",
            message=(
                f"Archive “{word}”? It leaves practice and deck counts, "
                "but keeps progress, decks, and any flag."
            ),
        )

    def restore_view(self, request, object_id: str) -> TemplateResponse | HttpResponseRedirect:
        word = self._word_for_change(request, object_id)
        if word.archived_at is None:
            self.message_user(request, "Already active.", messages.INFO)
            return HttpResponseRedirect(reverse("admin:api_word_change", args=[word.pk]))
        if request.method == "POST":
            word.restore()
            self.log_change(request, word, [{"changed": {"fields": ["archived_at"]}}])
            self.message_user(request, "Restored.", messages.SUCCESS)
            return HttpResponseRedirect(reverse("admin:api_word_changelist"))
        return self._render_confirmation(
            request,
            word,
            title="Restore word",
            breadcrumb="Restore",
            message=(
                f"Restore “{word}”? Only the archive stamp is cleared; "
                "flags, decks, and progress stay as they are."
            ),
        )

    def _word_for_change(self, request, object_id: str) -> Word:
        word = self.get_object(request, unquote(object_id))
        if word is None:
            raise Http404
        if not self.has_change_permission(request, word):
            raise PermissionDenied
        return word

    def _render_confirmation(
        self,
        request,
        word: Word,
        *,
        title: str,
        breadcrumb: str,
        message: str,
    ) -> TemplateResponse:
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            "admin/api/word/archive_status_confirmation.html",
            {
                **self.admin_site.each_context(request),
                "title": title,
                "breadcrumb": breadcrumb,
                "message": message,
                "object": word,
                "opts": self.opts,
            },
        )


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
