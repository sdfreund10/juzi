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
        word = self.get_object(request, unquote(object_id))
        if word is None:
            raise Http404
        if not self.has_change_permission(request, word):
            raise PermissionDenied
        if request.method == "POST":
            if word.archived_at is None:
                word.archived_at = timezone.now()
                word.save(update_fields=["archived_at"])
                self.log_change(
                    request,
                    word,
                    [{"changed": {"fields": ["archived_at"]}}],
                )
                self.message_user(request, "Archived.", messages.SUCCESS)
            return HttpResponseRedirect(reverse("admin:api_word_changelist"))
        context = {
            **self.admin_site.each_context(request),
            "title": "Archive word",
            "object": word,
            "opts": self.opts,
            "media": self.media,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            "admin/api/word/archive_confirmation.html",
            context,
        )

    def restore_view(self, request, object_id):
        word = self.get_object(request, unquote(object_id))
        if word is None:
            raise Http404
        if not self.has_change_permission(request, word):
            raise PermissionDenied
        if request.method == "POST":
            if word.archived_at is not None:
                word.archived_at = None
                word.save(update_fields=["archived_at"])
                self.log_change(
                    request,
                    word,
                    [{"changed": {"fields": ["archived_at"]}}],
                )
                self.message_user(request, "Restored.", messages.SUCCESS)
            return HttpResponseRedirect(reverse("admin:api_word_changelist"))
        context = {
            **self.admin_site.each_context(request),
            "title": "Restore word",
            "object": word,
            "opts": self.opts,
            "media": self.media,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            "admin/api/word/restore_confirmation.html",
            context,
        )

    @admin.action(description="Archive selected words", permissions=["change"])
    def archive_selected(self, request, queryset):
        # Use selected IDs directly so confirmation POSTs are not limited by the
        # default Active changelist filter.
        selected_ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        active = Word.objects.filter(pk__in=selected_ids, archived_at__isnull=True)
        if request.POST.get("post"):
            words = list(active)
            if words:
                now = timezone.now()
                word_ids = [word.pk for word in words]
                Word.objects.filter(pk__in=word_ids).update(archived_at=now)
                LogEntry.objects.log_actions(
                    user_id=request.user.pk,
                    queryset=words,
                    action_flag=CHANGE,
                    change_message=[{"changed": {"fields": ["archived_at"]}}],
                )
                self.message_user(
                    request,
                    f"Archived {len(words)} {model_ngettext(self.opts, len(words))}.",
                    messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    "None of the selected words were active.",
                    messages.WARNING,
                )
            return None

        opts = self.model._meta
        context = {
            **self.admin_site.each_context(request),
            "title": "Archive selected words",
            "queryset": active,
            "opts": opts,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "action_name": "archive_selected",
            "media": self.media,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            "admin/api/word/archive_selected_confirmation.html",
            context,
        )

    @admin.action(description="Restore selected words", permissions=["change"])
    def restore_selected(self, request, queryset):
        selected_ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        archived = Word.objects.filter(pk__in=selected_ids, archived_at__isnull=False)
        if request.POST.get("post"):
            words = list(archived)
            if words:
                word_ids = [word.pk for word in words]
                Word.objects.filter(pk__in=word_ids).update(archived_at=None)
                LogEntry.objects.log_actions(
                    user_id=request.user.pk,
                    queryset=words,
                    action_flag=CHANGE,
                    change_message=[{"changed": {"fields": ["archived_at"]}}],
                )
                self.message_user(
                    request,
                    f"Restored {len(words)} {model_ngettext(self.opts, len(words))}.",
                    messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    "None of the selected words were archived.",
                    messages.WARNING,
                )
            return None

        opts = self.model._meta
        context = {
            **self.admin_site.each_context(request),
            "title": "Restore selected words",
            "queryset": archived,
            "opts": opts,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "action_name": "restore_selected",
            "media": self.media,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            "admin/api/word/restore_selected_confirmation.html",
            context,
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
