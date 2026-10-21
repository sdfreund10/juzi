from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.utils import model_ngettext, unquote
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
from django.utils import timezone

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
        # Default (missing or "active"): keep archived words out of the queue.
        return queryset.filter(archived_at__isnull=True)

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
    actions = ("archive_selected", "restore_selected")
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
                "fields": ("reporter", "archived_at"),
            },
        ),
    )

    @admin.display(description="Reporter")
    def reporter(self, obj: Word) -> str:
        if obj.flagged_by_id is None:
            return "—"
        return str(obj.flagged_by)

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        return [
            path(
                "<path:object_id>/archive/",
                self.admin_site.admin_view(self.archive_view),
                name=f"{info[0]}_{info[1]}_archive",
            ),
            path(
                "<path:object_id>/restore/",
                self.admin_site.admin_view(self.restore_view),
                name=f"{info[0]}_{info[1]}_restore",
            ),
        ] + super().get_urls()

    def has_delete_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        word = None
        if object_id is not None:
            word = self.get_object(request, object_id)
        can_change = bool(word is not None and self.has_change_permission(request, word))
        extra_context["show_save_and_unflag"] = bool(
            can_change and word is not None and word.flagged_by_id is not None
        )
        extra_context["show_archive_link"] = bool(
            can_change and word is not None and word.archived_at is None
        )
        extra_context["show_restore_link"] = bool(
            can_change and word is not None and word.archived_at is not None
        )
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

    def archive_view(self, request, object_id):
        return self._object_archive_status_view(request, object_id, archive=True)

    def restore_view(self, request, object_id):
        return self._object_archive_status_view(request, object_id, archive=False)

    @admin.action(description="Archive selected words", permissions=["change"])
    def archive_selected(self, request, queryset):
        return self._bulk_archive_status_action(request, archive=True)

    @admin.action(description="Restore selected words", permissions=["change"])
    def restore_selected(self, request, queryset):
        return self._bulk_archive_status_action(request, archive=False)

    def _apply_archive_state(self, request, words, *, archive: bool) -> int:
        words = list(words)
        if not words:
            return 0
        word_ids = [word.pk for word in words]
        Word.objects.filter(pk__in=word_ids).update(archived_at=timezone.now() if archive else None)
        LogEntry.objects.log_actions(
            user_id=request.user.pk,
            queryset=words,
            action_flag=CHANGE,
            change_message=[{"changed": {"fields": ["archived_at"]}}],
        )
        return len(words)

    def _archive_status_confirmation(
        self,
        request,
        *,
        title: str,
        breadcrumb: str,
        message: str,
        empty_message: str = "",
        obj: Word | None = None,
        queryset=None,
        action_name: str | None = None,
    ):
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            "admin/api/word/archive_status_confirmation.html",
            {
                **self.admin_site.each_context(request),
                "title": title,
                "breadcrumb": breadcrumb,
                "message": message,
                "empty_message": empty_message,
                "object": obj,
                "queryset": queryset,
                "opts": self.opts,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                "action_name": action_name,
                "media": self.media,
            },
        )

    def _object_archive_status_view(self, request, object_id, *, archive: bool):
        word = self.get_object(request, unquote(object_id))
        if word is None:
            raise Http404
        if not self.has_change_permission(request, word):
            raise PermissionDenied

        eligible = word.archived_at is None if archive else word.archived_at is not None
        if request.method == "POST":
            if eligible:
                self._apply_archive_state(request, [word], archive=archive)
                self.message_user(
                    request,
                    "Archived." if archive else "Restored.",
                    messages.SUCCESS,
                )
            return HttpResponseRedirect(reverse("admin:api_word_changelist"))

        if archive:
            message = (
                f"Archive “{word}”? It leaves practice and deck counts, "
                "but keeps progress, decks, and any flag."
            )
        else:
            message = (
                f"Restore “{word}”? Only the archive stamp is cleared; "
                "flags, decks, and progress stay as they are."
            )
        return self._archive_status_confirmation(
            request,
            title="Archive word" if archive else "Restore word",
            breadcrumb="Archive" if archive else "Restore",
            message=message,
            obj=word,
        )

    def _bulk_archive_status_action(self, request, *, archive: bool):
        # Selected IDs, not the changelist queryset: confirmation POSTs must not
        # be limited by the default Active filter.
        selected_ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        words = Word.objects.filter(
            pk__in=selected_ids,
            archived_at__isnull=archive,
        )
        action_name = "archive_selected" if archive else "restore_selected"
        if request.POST.get("post"):
            count = self._apply_archive_state(request, words, archive=archive)
            if count:
                verb = "Archived" if archive else "Restored"
                self.message_user(
                    request,
                    f"{verb} {count} {model_ngettext(self.opts, count)}.",
                    messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    (
                        "None of the selected words were active."
                        if archive
                        else "None of the selected words were archived."
                    ),
                    messages.WARNING,
                )
            return None

        if archive:
            message = (
                "Archive the selected words? They leave practice and deck counts, "
                "but keep progress, decks, and flags."
            )
            empty_message = "None of the selected words are active."
        else:
            message = "Restore the selected words? Only the archive stamp is cleared."
            empty_message = "None of the selected words are archived."
        return self._archive_status_confirmation(
            request,
            title="Archive selected words" if archive else "Restore selected words",
            breadcrumb="Archive selected words" if archive else "Restore selected words",
            message=message,
            empty_message=empty_message,
            queryset=words,
            action_name=action_name,
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
