"""Page Object Models for Omnix UI."""

from .base_page import BasePage
from .chat_page import ChatPage
from .sidebar_page import SidebarPage
from .header_page import HeaderPage
from .settings_page import SettingsPage
from .audiobook_page import AudiobookPage
from .podcast_page import PodcastPage
from .voice_studio_page import VoiceStudioPage
from .voice_clone_page import VoiceClonePage
from .search_page import SearchPage

__all__ = [
    "BasePage",
    "ChatPage",
    "SidebarPage",
    "HeaderPage",
    "SettingsPage",
    "AudiobookPage",
    "PodcastPage",
    "VoiceStudioPage",
    "VoiceClonePage",
    "SearchPage",
]
