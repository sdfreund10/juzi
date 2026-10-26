from django.urls import path

from .auth_views import login_view, logout_view, me, set_proficiency_level
from .study_views import (
    categories,
    create_session,
    flag_word,
    rate_card,
    undo_card_rating,
    word_detail,
    words,
)
from .views import health

urlpatterns = [
    path("health/", health, name="health"),
    path("auth/me/", me, name="auth-me"),
    path("auth/login/", login_view, name="auth-login"),
    path("auth/logout/", logout_view, name="auth-logout"),
    path("auth/proficiency-level/", set_proficiency_level, name="auth-proficiency-level"),
    path("categories/", categories, name="categories"),
    path("sessions/", create_session, name="sessions-create"),
    path("ratings/", rate_card, name="ratings-create"),
    path("ratings/undo/", undo_card_rating, name="ratings-undo"),
    path("word-flags/", flag_word, name="word-flags-create"),
    path("words/", words, name="words-list"),
    path("words/<int:word_id>/", word_detail, name="words-detail"),
]
