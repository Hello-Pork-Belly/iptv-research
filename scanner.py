import urllib.request
import urllib.error
import subprocess
import concurrent.futures
import time
import re
import os

# We use global aggregators that collect from TG, as well as direct M3U links.
# These contain a lot of international / HK / TW sources.
SEED_URLS = [
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/hk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/tw.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://raw.githubusercontent.com/yuanzl77/IPTV/main/live.txt"
]

# Strictly Hong Kong and Taiwan keywords. NO CCTV, NO Mainland Satellite.
TARGET_CHANNELS = [
    "香港", "台湾", "TVB", "翡翠", "明珠", "J2", "无锡新闻",
    "凤凰", "东森", "中天", "纬来", "民视", "三立", "华视", "台视", "中视", 
    "年代", "非凡", "八大", "ViuTV", "HOY", "有线", "星空", "HBO", "FOX", "DISCOVERY",
    "HK", "TW"
]

# Exclude list to filter out falsely matched mainland channels or irrelevant stuff
EXCLUDE_KEYWORDS = ["CCTV", "卫视", "内蒙", "新疆", "新闻联播", "中央"]

MAX_URLS_PER_CHANNEL = 10

def download_list(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return ""

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
                # Remove suffix like $LR... from txt sources
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

def is_target_channel(name):
    name_upper = name.upper()
    
    # Check exclude list first
    for exclude in EXCLUDE_KEYWORDS:
        if exclude.upper() in name_upper:
            return False
            
    # Then check target list
    for target in TARGET_CHANNELS:
        if target.upper() in name_upper:
            return True
    return False

def main():
    print("Starting HK/TW Exclusive IPTV Scanner...")
    all_channels = []
    
    for url in SEED_URLS:
        print(f"Downloading from: {url}")
        content = download_list(url)
        parsed = parse_m3u_or_txt(content)
        all_channels.extend(parsed)
        print(f"Found {len(parsed)} streams.")
        
    # Load Blacklist
    blacklist = set()
    if os.path.exists("blacklist.txt"):
        with open("blacklist.txt", "r", encoding="utf-8") as bf:
            for line in bf:
                bl_url = line.strip()
                if bl_url:
                    blacklist.add(bl_url)
    print(f"Loaded {len(blacklist)} dead URLs from blacklist.")

    candidate_dict = {}
    for name, url in all_channels:
        if is_target_channel(name):
            if url in blacklist:
                continue
            clean_name = name.replace("高清", "").replace("1080P", "").replace("FHD", "").strip()
            # Clean up messy TG tags
            clean_name = re.sub(r'\[.*?\]', '', clean_name).strip()
            
            if clean_name not in candidate_dict:
                candidate_dict[clean_name] = []
            if url not in candidate_dict[clean_name]:
                candidate_dict[clean_name].append(url)
            
    print(f"\nFiltered down to {len(candidate_dict)} unique HK/TW channels.")
    
    final_dict = {}
    # Bypass ffprobe testing as US servers timeout on Asian proxy IPs
    for channel_name, urls in candidate_dict.items():
        # Keep up to MAX_URLS_PER_CHANNEL
        final_dict[channel_name] = urls[:MAX_URLS_PER_CHANNEL]
        print(f"Added {len(final_dict[channel_name])} URLs for {channel_name}.")

    output_file = "best_tv.m3u"
    print(f"\nWriting results to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U x-tvg-url="https://live.fanmingming.com/e.xml"\n')
        for name, urls in final_dict.items():
            if not urls:
                continue
            
            # Simple grouping
            group = "港台频道"
            if "凤凰" in name or "TVB" in name.upper() or "翡翠" in name:
                group = "香港频道"
            elif "东森" in name or "中天" in name or "纬来" in name or "民视" in name or "三立" in name:
                group = "台湾频道"
                
            logo_url = f"https://live.fanmingming.com/tv/{urllib.parse.quote(name)}.png"
            
            for url in urls:
                f.write(f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n')
                f.write(f'{url}\n')

    print("Scanner finished successfully!")

if __name__ == "__main__":
    main()
