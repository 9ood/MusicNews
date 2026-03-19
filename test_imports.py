#!/usr/bin/env python3
import sys
print("1. Starting import test...", flush=True)

print("2. Importing sys...", flush=True)
import sys

print("3. Importing src.hotspot_fetcher...", flush=True)
from src.hotspot_fetcher import HotspotFetcher

print("4. Importing src.topic_generator...", flush=True)
from src.topic_generator import TopicGenerator

print("5. Importing src.emailer...", flush=True)
from src.emailer import EmailSender

print("6. Importing src.utils...", flush=True)
from src.utils import setup_logger, get_date_str

print("7. All imports successful!", flush=True)
