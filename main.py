from dotenv import load_dotenv

load_dotenv()

import os
import re
import requests
import asyncio
import base64
import shutil

from urllib.parse import (
    urlparse,
    parse_qsl,
    urlencode,
    urlunparse
)

from telethon import TelegramClient, events
from telethon.errors import RPCError
from telethon.sessions import SQLiteSession

print("=== SECRETS DEBUG ===")

if os.path.exists("/etc/secrets"):
    print("✅ /etc/secrets exists")
    print("FILES:", os.listdir("/etc/secrets"))
else:
    print("❌ /etc/secrets does not exist")
    

SESSION_SECRET = "/etc/secrets/vorora_telegram.session"
SESSION_FILE = "/tmp/vorora_telegram.session"

# Base64 secret ne actual .session SQLite file ma convert karo
with open(SESSION_SECRET, "rb") as f:
    encoded = f.read()

with open(SESSION_FILE, "wb") as f:
    f.write(base64.b64decode(encoded))

# ============================================================
# CONFIG
# ============================================================

API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ TG_BOT_TOKEN missing in .env")


# ============================================================
# CHANNEL PAIRS
#
# SOURCE                         DESTINATION
#
# indian_online_offer       ->   dailyofferguru
# dailyofferjunction        ->   offersandloafers
# ============================================================

CHANNEL_PAIRS = os.getenv("TG_CHANNEL_PAIRS")

if not CHANNEL_PAIRS:
    raise ValueError(
        "❌ TG_CHANNEL_PAIRS missing in .env"
    )


CHANNEL_MAP = {}


for pair in CHANNEL_PAIRS.split(","):

    pair = pair.strip()

    if not pair:
        continue

    if ":" not in pair:
        raise ValueError(
            f"❌ Invalid pair: {pair}\n"
            f"Use: source:destination"
        )

    source, destination = pair.split(":", 1)

    source = source.strip().lstrip("@").lower()
    destination = destination.strip().lstrip("@")

    if not source or not destination:
        raise ValueError(
            f"❌ Invalid channel pair: {pair}"
        )

    CHANNEL_MAP[source] = destination


# ============================================================
# AMAZON
# ============================================================

AMAZON_TAG = os.getenv("AMAZON_TAG")


# ============================================================
# CUELINKS
# ============================================================

CUELINKS_API_KEY = os.getenv("CUELINKS_API_KEY")

CUELINKS_API_URL = (
    "https://developers.cuelinks.com/pub_api/v3/links/convert"
)


# ============================================================
# USER CLIENT
#
# USER ACCOUNT:
# READS SOURCE CHANNELS
# ============================================================

client = TelegramClient(
    SQLiteSession("/tmp/vorora_telegram"),
    API_ID,
    API_HASH
)

# ============================================================
# BOT CLIENT
#
# BOT:
# POSTS DESTINATION CHANNELS
# ============================================================

bot = TelegramClient(
    "telegram_bot",
    API_ID,
    API_HASH
)


# ============================================================
# PRINT CHANNEL PAIRS
# ============================================================

print("\n")
print("==========================================")
print("📡 CHANNEL PAIRS")
print("==========================================")

for source, destination in CHANNEL_MAP.items():

    print(
        f"📥 @{source}"
        f"  →  "
        f"📤 @{destination}"
    )

print("==========================================")
print()


# ============================================================
# FIND URLS
# ============================================================

def find_urls(text):

    return re.findall(
        r'https?://[^\s<>"\']+',
        text
    )


# ============================================================
# CLEAN URL
# ============================================================

def clean_url(url):

    return url.rstrip(
        ".,!?;:)]}>"
    )


# ============================================================
# RESOLVE SHORT URL
# ============================================================

def resolve_url(url):

    try:

        response = requests.get(
            url,
            allow_redirects=True,
            timeout=20,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/139.0 Safari/537.36"
                )
            }
        )

        final_url = response.url

        print("\n🔀 REDIRECT")
        print("FROM:", url)
        print("TO  :", final_url)

        return final_url

    except Exception as e:

        print(
            "\n❌ Redirect error:",
            e
        )

        return url


# ============================================================
# DETECT PLATFORM
# ============================================================

def detect_platform(url):

    url_lower = url.lower()

    if (
        "amazon.in" in url_lower
        or "amazon.com" in url_lower
        or "amzn.to" in url_lower
        or "amzn.in" in url_lower
    ):
        return "amazon"

    if (
        "flipkart.com" in url_lower
        or "fkrt.co" in url_lower
    ):
        return "flipkart"

    if (
        "myntra.com" in url_lower
        or "myntr.in" in url_lower
    ):
        return "myntra"

    if (
        "ajio.com" in url_lower
        or "ajiio.in" in url_lower
    ):
        return "ajio"

    if (
        "meesho.com" in url_lower
        or "meesho" in url_lower
    ):
        return "meesho"

    return "other"


# ============================================================
# AMAZON CLEAN
# ============================================================

def clean_amazon_url(url):

    try:

        parsed = urlparse(url)

        query_params = parse_qsl(
            parsed.query,
            keep_blank_values=True
        )

        remove_params = {
            "tag",
            "ascsubtag",
            "linkCode",
            "linkId",
            "camp",
            "creative",
            "creativeASIN",
            "ref_",
            "ref",
            "psc"
        }

        cleaned_params = [
            (key, value)
            for key, value in query_params
            if key not in remove_params
        ]

        cleaned_query = urlencode(
            cleaned_params
        )

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                cleaned_query,
                parsed.fragment
            )
        )

    except Exception as e:

        print(
            "❌ Amazon URL cleaning error:",
            e
        )

        return url


# ============================================================
# AMAZON AFFILIATE
# ============================================================

def convert_amazon(url):

    if not AMAZON_TAG:

        print(
            "❌ AMAZON_TAG missing"
        )

        return None, False

    try:

        clean_value = clean_amazon_url(
            url
        )

        parsed = urlparse(
            clean_value
        )

        query_params = parse_qsl(
            parsed.query,
            keep_blank_values=True
        )

        query_params = [
            (key, value)
            for key, value in query_params
            if key.lower() != "tag"
        ]

        query_params.append(
            ("tag", AMAZON_TAG)
        )

        final_query = urlencode(
            query_params
        )

        affiliate_url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                final_query,
                parsed.fragment
            )
        )

        print(
            "\n💰 AMAZON AFFILIATE:"
        )

        print(
            affiliate_url
        )

        return affiliate_url, True

    except Exception as e:

        print(
            "\n❌ Amazon affiliate error:",
            e
        )

        return None, False


# ============================================================
# REMOVE TRACKING
# ============================================================

def clean_tracking_params(url):

    try:

        parsed = urlparse(url)

        params = parse_qsl(
            parsed.query,
            keep_blank_values=True
        )

        tracking_names = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "clickid",
            "click_id",
            "affid",
            "affExtParam1",
            "affExtParam2",
            "affiliate",
            "affiliate_id",
            "subid",
            "sub_id",
            "source",
            "campaign"
        }

        cleaned = [
            (key, value)
            for key, value in params
            if key.lower() not in {
                x.lower()
                for x in tracking_names
            }
        ]

        query = urlencode(
            cleaned
        )

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                query,
                parsed.fragment
            )
        )

    except Exception as e:

        print(
            "❌ Tracking cleanup error:",
            e
        )

        return url


# ============================================================
# CUELINKS
# ============================================================

def convert_with_cuelinks(url):

    if not CUELINKS_API_KEY:

        print(
            "❌ CUELINKS_API_KEY missing"
        )

        return None, False

    headers = {
        "Authorization":
            f"Token {CUELINKS_API_KEY}",

        "Content-Type":
            "application/json"
    }

    payload = {
        "url": url,
        "shorten": True
    }

    try:

        response = requests.post(
            CUELINKS_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        print(
            "\n💰 CUELINKS HTTP:",
            response.status_code
        )

        if response.status_code != 200:

            print(
                "❌ Cuelinks error:",
                response.text
            )

            return None, False

        result = response.json()

        data = result.get(
            "data",
            {}
        )

        affiliated = data.get(
            "affiliated",
            False
        )

        tracking_url = data.get(
            "tracking_url"
        )

        short_url = data.get(
            "short_url"
        )

        print(
            "Campaign:",
            data.get("campaign")
        )

        print(
            "Affiliate:",
            affiliated
        )

        if affiliated:

            affiliate_url = (
                short_url
                or tracking_url
            )

            if affiliate_url:

                print(
                    "\n✅ CUELINKS LINK:"
                )

                print(
                    affiliate_url
                )

                return affiliate_url, True

        print(
            "\n⚠️ Cuelinks affiliate unavailable"
        )

        return None, False

    except Exception as e:

        print(
            "\n❌ Cuelinks exception:",
            e
        )

        return None, False


# ============================================================
# PROCESS URL
# ============================================================

def process_url(original_url):

    original_url = clean_url(
        original_url
    )

    final_url = resolve_url(
        original_url
    )

    platform = detect_platform(
        final_url
    )

    print("\n")
    print("--------------------------------------")
    print("ORIGINAL :", original_url)
    print("FINAL    :", final_url)
    print("PLATFORM :", platform)
    print("--------------------------------------")


    # AMAZON

    if platform == "amazon":

        affiliate_url, success = (
            convert_amazon(
                final_url
            )
        )

        if success:
            return affiliate_url, True

        return original_url, False


    # CUELINKS

    if platform in {
        "flipkart",
        "myntra",
        "ajio",
        "meesho"
    }:

        clean_merchant_url = (
            clean_tracking_params(
                final_url
            )
        )

        affiliate_url, success = (
            convert_with_cuelinks(
                clean_merchant_url
            )
        )

        if success:
            return affiliate_url, True

        return original_url, False


    # UNKNOWN

    return original_url, False


# ============================================================
# PROCESS MESSAGE
# ============================================================

def process_message(text):

    urls = find_urls(
        text
    )

    print(
        "\n🔗 URLs FOUND:",
        len(urls)
    )

    converted_text = text

    for original_url in urls:

        original_url = clean_url(
            original_url
        )

        new_url, success = (
            process_url(
                original_url
            )
        )

        if success:

            converted_text = (
                converted_text.replace(
                    original_url,
                    new_url
                )
            )

    return converted_text


# ============================================================
# CHECK BOT DESTINATION ACCESS
# ============================================================

async def check_bot_destinations():

    print("\n")
    print("==========================================")
    print("🤖 CHECKING BOT DESTINATIONS")
    print("==========================================")


    for source, destination in CHANNEL_MAP.items():

        try:

            entity = await bot.get_entity(
                destination
            )

            print(
                f"\n✅ DESTINATION FOUND:"
                f" @{destination}"
            )

            print(
                f"   ID: {entity.id}"
            )

            # Check bot permissions

            try:

                permissions = await bot.get_permissions(
                    entity,
                    "me"
                )

                print(
                    f"   ADMIN: "
                    f"{permissions.is_admin}"
                )

                print(
                    f"   POST: "
                    f"{permissions.post_messages}"
                )

            except Exception as permission_error:

                print(
                    "   ⚠️ Permission check failed:"
                )

                print(
                    f"   {permission_error}"
                )

        except Exception as e:

            print(
                f"\n❌ DESTINATION ERROR:"
            )

            print(
                f"   @{destination}"
            )

            print(
                f"   {e}"
            )

    print("\n==========================================")


# ============================================================
# CHECK SOURCE ACCESS
# ============================================================

async def check_source_channels():

    print("\n")
    print("==========================================")
    print("👤 CHECKING SOURCE CHANNELS")
    print("==========================================")


    for source in CHANNEL_MAP.keys():

        try:

            entity = await client.get_entity(
                source
            )

            print(
                f"✅ SOURCE FOUND:"
                f" @{source}"
            )

            print(
                f"   ID: {entity.id}"
            )

        except Exception as e:

            print(
                f"❌ SOURCE ERROR:"
                f" @{source}"
            )

            print(
                f"   {e}"
            )

    print("\n==========================================")


# ============================================================
# NEW MESSAGE HANDLER
# ============================================================

@client.on(
    events.NewMessage(
        incoming=True
    )
)
async def new_message_handler(event):

    try:

        chat = await event.get_chat()

        username = getattr(
            chat,
            "username",
            None
        )

        if not username:
            return

        source = username.lower()

        if source not in CHANNEL_MAP:
            return

        destination = CHANNEL_MAP[source]

        message = event.message

        text = message.text or ""

        print("\n\n")
        print("==========================================")
        print("🔥 NEW DEAL RECEIVED")
        print("==========================================")

        print(
            f"📥 SOURCE:"
            f" @{source}"
        )

        print(
            f"📤 DESTINATION:"
            f" @{destination}"
        )

        print(
            "\nMESSAGE:"
        )

        print(
            text
        )

        print(
            "=========================================="
        )


        # ====================================================
        # PROCESS LINKS
        # ====================================================

        converted_text = await asyncio.to_thread(
            process_message,
            text
        )


        # ====================================================
        # POST USING BOT
        # ====================================================

        destination_entity = await bot.get_entity(
            destination
        )


        if message.media:

            # IMPORTANT:
            # Download media using USER CLIENT first.
            # Then upload it using BOT CLIENT.

            media_path = await client.download_media(
                message
            )

            if media_path:

                try:

                    await bot.send_file(
                        destination_entity,
                        media_path,
                        caption=converted_text
                    )

                    print(
                        "\n✅ MEDIA + CAPTION POSTED"
                    )

                finally:

                    try:

                        os.remove(
                            media_path
                        )

                    except Exception:
                        pass

            else:

                print(
                    "\n⚠️ Media download failed"
                )

        else:

            await bot.send_message(
                destination_entity,
                converted_text
            )

            print(
                "\n✅ TEXT POSTED"
            )


    except Exception as e:

        print(
            "\n❌ FORWARDING ERROR:"
        )

        print(
            repr(e)
        )


    print("\n==========================================")
    print(
        "⏳ Waiting for next deal..."
    )
    print(
        "=========================================="
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    print("\n")
    print("==========================================")
    print("🚀 STARTING TELEGRAM FORWARDER")
    print("==========================================")


    # ========================================================
    # START USER CLIENT
    # ========================================================

    await client.connect()

    if not await client.is_user_authorized():
        raise RuntimeError(
            "❌ Telegram session is NOT authorized."
    )

    print(
        "✅ USER CLIENT CONNECTED"
    )


    # ========================================================
    # START BOT
    # ========================================================

    await bot.start(
        bot_token=BOT_TOKEN
    )

    print(
        "✅ BOT CONNECTED"
    )


    # ========================================================
    # BOT INFO
    # ========================================================

    me = await bot.get_me()

    print(
        "\n🤖 BOT:"
    )

    print(
        f"   @{me.username}"
    )

    print(
        f"   ID: {me.id}"
    )


    # ========================================================
    # CHECK SOURCE
    # ========================================================

    await check_source_channels()


    # ========================================================
    # CHECK DESTINATIONS
    # ========================================================

    await check_bot_destinations()


    # ========================================================
    # RUN
    # ========================================================

    print("\n")
    print("==========================================")
    print("🟢 FORWARDER RUNNING")
    print("==========================================")

    for source, destination in CHANNEL_MAP.items():

        print(
            f"📥 @{source}"
            f"  →  "
            f"🤖 @{destination}"
        )

    print("==========================================")
    print()


    await client.run_until_disconnected()


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )