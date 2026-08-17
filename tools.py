# tools.py

import logging
import os
import subprocess
import webbrowser
import time
import wikipedia

from langchain_community.tools import DuckDuckGoSearchRun
from livekit.agents import function_tool, RunContext

logging.basicConfig(level=logging.INFO)


@function_tool()
async def open_file_explorer(context: RunContext) -> str:
    try:
        subprocess.Popen(["explorer", "/n,", "C:\\"])
        logging.info("Opened new File Explorer window.")
        return "Opened a new File Explorer window, Sir."
    except Exception as e:
        logging.error(f"Error opening File Explorer: {e}")
        return f"Failed to open File Explorer, Sir. {e}"


@function_tool()
async def open_default_browser(context: RunContext) -> str:
    try:
        url = f"https://www.google.com/?nocache={time.time()}"
        webbrowser.open(url, new=2)
        logging.info(f"Opened default web browser to: {url}")
        return "Opened your default browser to Google, Sir."
    except Exception as e:
        logging.error(f"Error opening default browser: {e}")
        return "An error occurred while opening your default browser, Sir."


@function_tool()
async def get_weather(context: RunContext, city: str) -> str:
    try:
        query = f"current temperature in {city}"
        result = DuckDuckGoSearchRun().run(tool_input=query)
        logging.info(f"Weather search result for {city}: {result}")
        return f"{result}, Sir."
    except Exception as e:
        logging.error(f"Error retrieving weather for {city}: {e}")
        return "An error occurred while retrieving the weather, Sir."


@function_tool()
async def open_website(context: RunContext, url: str) -> str:
    try:
        webbrowser.open(url, new=2)
        logging.info(f"Opened website: {url}")
        return f"Opened {url}, Sir."
    except Exception as e:
        logging.error(f"Error opening website {url}: {e}")
        return f"An error occurred while opening {url}, Sir."


@function_tool()
async def play_music(context: RunContext, file_path: str) -> str:
    try:
        os.startfile(file_path)
        logging.info(f"Playing music: {file_path}")
        return f"Playing your music file, Sir."
    except Exception as e:
        logging.error(f"Error playing music: {e}")
        return "An error occurred while playing your music, Sir."


@function_tool()
async def play_youtube_music(context: RunContext, query: str) -> str:
    try:
        search_query = query.replace(" ", "+")
        youtube_url = f"https://www.youtube.com/results?search_query={search_query}&nocache={time.time()}"
        webbrowser.open(youtube_url, new=2)
        logging.info(f"Searching YouTube for: {query}")
        return f"Opened YouTube for '{query}', Sir."
    except Exception as e:
        logging.error(f"Error opening YouTube for '{query}': {e}")
        return "An error occurred while opening YouTube, Sir."


@function_tool()
async def search_web(context: RunContext, query: str) -> str:
    try:
        result = DuckDuckGoSearchRun().run(tool_input=query)
        logging.info(f"DuckDuckGo result for '{query}': {result}")

        if result and len(result.strip()) > 0:
            return f"{result}, Sir."

        summary = wikipedia.summary(query, sentences=2)
        logging.info(f"Wikipedia fallback for '{query}': {summary}")
        return f"{summary}, Sir."

    except Exception as e:
        logging.error(f"Error during search for '{query}': {e}")
        return f"An error occurred while retrieving that information, Sir."