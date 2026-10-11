# tools.py

import logging
import os
import subprocess
import webbrowser
import time
import wikipedia
from urllib.parse import quote_plus

from langchain_community.tools import DuckDuckGoSearchRun
from livekit.agents import function_tool, RunContext


# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wolf-tools")


# ---------------------------------------------------------
# OPEN FILE EXPLORER
# ---------------------------------------------------------

@function_tool()
async def open_file_explorer(context: RunContext) -> str:
    """
    Open Windows File Explorer.
    """

    try:
        subprocess.Popen(["explorer", "/n,", "C:\\"])

        logger.info("Opened File Explorer.")

        return "Opened a new File Explorer window, Sir."

    except Exception as e:
        logger.error(f"Error opening File Explorer: {e}")

        return f"Failed to open File Explorer, Sir. {e}"


# ---------------------------------------------------------
# OPEN DEFAULT BROWSER
# ---------------------------------------------------------

@function_tool()
async def open_default_browser(context: RunContext) -> str:
    """
    Open Google in the default browser.
    """

    try:
        url = "https://www.google.com/"

        webbrowser.open(url, new=2)

        logger.info(f"Opened browser: {url}")

        return "Opened Google in your default browser, Sir."

    except Exception as e:
        logger.error(f"Error opening default browser: {e}")

        return "An error occurred while opening your default browser, Sir."


# ---------------------------------------------------------
# SEARCH GOOGLE
# ---------------------------------------------------------

@function_tool()
async def search_google(context: RunContext, query: str) -> str:
    """
    Search Google for the user's query.

    Example:
    search_google("latest research papers on voice assistants")
    """

    try:

        # Remove unnecessary spaces
        query = query.strip()

        if not query:
            logger.warning("Google search called with empty query.")

            return "I need something to search for, Sir."

        # Convert query into URL-safe format
        encoded_query = quote_plus(query)

        # Create actual Google search URL
        google_url = (
            f"https://www.google.com/search?q={encoded_query}"
        )

        logger.info(
            f"Google search query: {query}"
        )

        logger.info(
            f"Google search URL: {google_url}"
        )

        # Open actual search results
        webbrowser.open(
            google_url,
            new=2
        )

        return (
            f"I searched Google for '{query}', Sir."
        )

    except Exception as e:

        logger.error(
            f"Error searching Google for '{query}': {e}"
        )

        return (
            "An error occurred while searching Google, Sir."
        )


# ---------------------------------------------------------
# WEATHER
# ---------------------------------------------------------

@function_tool()
async def get_weather(
    context: RunContext,
    city: str
) -> str:

    try:

        city = city.strip()

        query = f"current weather in {city}"

        result = DuckDuckGoSearchRun().run(
            tool_input=query
        )

        logger.info(
            f"Weather search result for {city}: {result}"
        )

        if result:
            return f"{result}, Sir."

        return (
            f"I could not find the current weather "
            f"for {city}, Sir."
        )

    except Exception as e:

        logger.error(
            f"Error retrieving weather for {city}: {e}"
        )

        return (
            "An error occurred while retrieving "
            "the weather, Sir."
        )


# ---------------------------------------------------------
# OPEN WEBSITE
# ---------------------------------------------------------

@function_tool()
async def open_website(
    context: RunContext,
    url: str
) -> str:

    try:

        url = url.strip()

        # If user/tool gives only domain name
        if not url.startswith(
            ("http://", "https://")
        ):
            url = "https://" + url

        webbrowser.open(
            url,
            new=2
        )

        logger.info(
            f"Opened website: {url}"
        )

        return f"Opened {url}, Sir."

    except Exception as e:

        logger.error(
            f"Error opening website {url}: {e}"
        )

        return (
            f"An error occurred while opening "
            f"{url}, Sir."
        )


# ---------------------------------------------------------
# PLAY LOCAL MUSIC
# ---------------------------------------------------------

@function_tool()
async def play_music(
    context: RunContext,
    file_path: str
) -> str:

    try:

        file_path = file_path.strip()

        if not os.path.exists(file_path):
            return (
                f"I could not find the music file "
                f"at {file_path}, Sir."
            )

        os.startfile(file_path)

        logger.info(
            f"Playing music: {file_path}"
        )

        return "Playing your music file, Sir."

    except Exception as e:

        logger.error(
            f"Error playing music: {e}"
        )

        return (
            "An error occurred while playing "
            "your music, Sir."
        )


# ---------------------------------------------------------
# SEARCH / PLAY YOUTUBE MUSIC
# ---------------------------------------------------------

@function_tool()
async def play_youtube_music(
    context: RunContext,
    query: str
) -> str:

    try:

        query = query.strip()

        if not query:
            return (
                "Please tell me what you want "
                "to play on YouTube, Sir."
            )

        encoded_query = quote_plus(query)

        youtube_url = (
            "https://www.youtube.com/results"
            f"?search_query={encoded_query}"
        )

        webbrowser.open(
            youtube_url,
            new=2
        )

        logger.info(
            f"YouTube search: {query}"
        )

        return (
            f"Opened YouTube search for "
            f"'{query}', Sir."
        )

    except Exception as e:

        logger.error(
            f"Error opening YouTube for "
            f"'{query}': {e}"
        )

        return (
            "An error occurred while opening "
            "YouTube, Sir."
        )


# ---------------------------------------------------------
# WEB SEARCH - DUCKDUCKGO
# ---------------------------------------------------------

@function_tool()
async def search_web(
    context: RunContext,
    query: str
) -> str:

    try:

        query = query.strip()

        if not query:
            return (
                "Please tell me what you want "
                "me to search for, Sir."
            )

        logger.info(
            f"Web search query: {query}"
        )

        result = DuckDuckGoSearchRun().run(
            tool_input=query
        )

        if result and result.strip():

            logger.info(
                f"DuckDuckGo result received "
                f"for: {query}"
            )

            return f"{result}, Sir."

        # -------------------------------------------------
        # WIKIPEDIA FALLBACK
        # -------------------------------------------------

        try:

            summary = wikipedia.summary(
                query,
                sentences=2
            )

            logger.info(
                f"Wikipedia fallback used "
                f"for: {query}"
            )

            return f"{summary}, Sir."

        except Exception:

            return (
                f"I could not find useful information "
                f"for '{query}', Sir."
            )

    except Exception as e:

        logger.error(
            f"Error during web search "
            f"for '{query}': {e}"
        )

        return (
            "An error occurred while retrieving "
            "that information, Sir."
        )

        