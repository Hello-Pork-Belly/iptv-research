import os
import re
import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime, timedelta, timezone

# 1. Credentials from GitHub Secrets
API_ID = int(os.environ.get("TG_API_ID", 0))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_STRING = os.environ.get("TG_SESSION", "")

# 2. Target Telegram Groups
TARGET_CHATS = ["@tvzby", "@tmxktg"]

# 3. Filtering Rules (HK/TW only)
TARGET_CHANNELS = [
    "香港", "台湾", "TVB", "翡翠", "明珠", "J2", 
    "凤凰", "东森", "中天", "纬来", "民视", "三立", "华视", "台视", "中视", 
    "年代", "非凡", "八大", "ViuTV", "HOY", "有线", "星空", "HBO", "FOX", "DISCOVERY",
    "HK", "TW"
]
EXCLUDE_KEYWORDS = ["CCTV", "卫视", "内蒙", "新疆", "新闻联播", "中央"]

def is_target_channel(name):
    name_upper = name.upper()
    for exclude in EXCLUDE_KEYWORDS:
        if exclude.upper() in name_upper:
            return False
    for target in TARGET_CHANNELS:
        if target.upper() in name_upper:
            return True
    return False

def parse_m3u_or_txt(content):
    channels = []
    lines = content.split('\n')
    current_name = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if line.startswith("#EXTINF"):
            parts = line.split(',')
            if len(parts) > 1:
                current_name = parts[-1].strip()
        elif line.startswith("http"):
            if current_name:
                url = line.split('$')[0]
                channels.append((current_name, url))
                current_name = ""
            else:
                url = line.split('$')[0]
                channels.append(("Unknown", url))
        elif "," in line and "http" in line:
            parts = line.split(',')
            if len(parts) == 2:
                name = parts[0].strip()
                url = parts[1].split('$')[0].strip()
                if url.startswith("http"):
                    channels.append((name, url))
    return channels

async def main():
    if not SESSION_STRING:
        print("Missing TG credentials in environment variables! Please set them in GitHub Secrets.")
        return

    print("Starting Deep TG Scanner (Userbot Mode)...")

    # Load Blacklist
    blacklist = set()
    if os.path.exists("blacklist.txt"):
        with open("blacklist.txt", "r", encoding="utf-8") as bf:
            for line in bf:
                bl_url = line.strip()
                if bl_url:
                    blacklist.add(bl_url)
    print(f"Loaded {len(blacklist)} dead URLs from blacklist.")

    # Load existing best_tv.m3u so we don't lose channels we already found
    existing_channels = []
    if os.path.exists("best_tv.m3u"):
        with open("best_tv.m3u", "r", encoding="utf-8") as ef:
            existing_channels = parse_m3u_or_txt(ef.read())
            
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    
    all_channels = []
    
    # Scan the last 3 days of messages
    time_limit = datetime.now(timezone.utc) - timedelta(days=3)
    
    for chat in TARGET_CHATS:
        print(f"Scanning {chat}...")
        try:
            # We iterate messages starting from newest, going back up to time_limit
            async for message in client.iter_messages(chat, offset_date=None, reverse=False):
                if message.date < time_limit:
                    break # Stop if we reach messages older than 3 days
                    
                # 1. Parse message text
                if message.text:
                    parsed = parse_m3u_or_txt(message.text)
                    all_channels.extend(parsed)
                
                # 2. Parse file attachments (.m3u, .txt)
                if message.document:
                    filename = None
                    for attr in message.document.attributes:
                        if hasattr(attr, 'file_name'):
                            filename = attr.file_name
                            break
                    if filename and (filename.endswith(".txt") or filename.endswith(".m3u")):
                        print(f"Downloading attachment: {filename}")
                        file_bytes = await client.download_media(message, bytes)
                        try:
                            content = file_bytes.decode('utf-8', errors='ignore')
                            parsed = parse_m3u_or_txt(content)
                            all_channels.extend(parsed)
                        except Exception as e:
                            print(f"Error decoding {filename}: {e}")
                            
                await asyncio.sleep(0.05) # Anti-ban delay
        except Exception as e:
            print(f"Failed to scan {chat}: {e}")
            
    await client.disconnect()
    
    print(f"Total raw streams extracted from TG: {len(all_channels)}")
    
    # Merge existing channels with newly found channels
    all_channels.extend(existing_channels)
    
    candidate_dict = {}
    for name, url in all_channels:
        if is_target_channel(name):
            if url in blacklist:
                continue
            clean_name = name.replace("高清", "").replace("1080P", "").replace("FHD", "").strip()
            clean_name = re.sub(r'\[.*?\]', '', clean_name).strip()
            
            if clean_name not in candidate_dict:
                candidate_dict[clean_name] = []
            if url not in candidate_dict[clean_name]:
                candidate_dict[clean_name].append(url)

    print(f"\nFiltered down to {len(candidate_dict)} unique HK/TW channels (Excluding Blacklist).")
    output_file = "best_tv.m3u"
    
    final_count = 0
    with open(output_file, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url="https://live.fanmingming.com/e.xml"\n')
        for channel_name, urls in candidate_dict.items():
            for url in urls[:10]:
                f.write(f'#EXTINF:-1 group-title="港台精选",{channel_name}\n')
                f.write(f'{url}\n')
                final_count += 1
                
    print(f"Successfully wrote {final_count} URLs to {output_file}.")

if __name__ == '__main__':
    asyncio.run(main())
