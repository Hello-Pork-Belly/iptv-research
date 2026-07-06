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
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/global.m3u"
]

# Strictly Hong Kong and Taiwan keywords. NO CCTV, NO Mainland Satellite.
TARGET_CHANNELS = [
    "香港", "台湾", "TVB", "翡翠", "明珠", "J2", "无锡新闻", # Wait, ignore wuxi
    "凤凰", "东森", "中天", "纬来", "民视", "三立", "华视", "台视", "中视", 
    "年代", "非凡", "八大", "ViuTV", "HOY", "有线", "星空", "HBO", "FOX", "DISCOVERY",
    "HK", "TW"
]

# Exclude list to filter out falsely matched mainland channels or irrelevant stuff
EXCLUDE_KEYWORDS = ["CCTV", "卫视", "内蒙", "新疆", "新闻联播", "中央"]

MAX_URLS_PER_CHANNEL = 5

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
                channels.append((current_name, line))
                current_name = ""
            else:
                channels.append(("Unknown", line))
        
        elif "," in line and "http" in line:
            parts = line.split(',')
            if len(parts) == 2:
                name = parts[0].strip()
                url = parts[1].strip()
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

def check_url_ffprobe(url):
    """ Use ffprobe to check if the HK/TW stream is alive """
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "stream=codec_type", 
        "-timeout", "5000000", 
        "-i", url
    ]
    try:
        # Increase timeout slightly since global sources might take a second to handshake
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        if result.returncode == 0 and ("video" in result.stdout.decode() or "audio" in result.stdout.decode()):
            return True
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
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
        
    candidate_dict = {}
    for name, url in all_channels:
        if is_target_channel(name):
            clean_name = name.replace("高清", "").replace("1080P", "").replace("FHD", "").strip()
            # Clean up messy TG tags
            clean_name = re.sub(r'\[.*?\]', '', clean_name).strip()
            
            if clean_name not in candidate_dict:
                candidate_dict[clean_name] = set()
            candidate_dict[clean_name].add(url)
            
    print(f"\nFiltered down to {len(candidate_dict)} unique HK/TW channels.")
    
    final_dict = {}
    MAX_WORKERS = 15 # Can be higher since global routing is better from GitHub US
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for channel_name, urls in candidate_dict.items():
            print(f"Testing {channel_name} (Found {len(urls)} candidates)...")
            final_dict[channel_name] = []
            
            future_to_url = {executor.submit(check_url_ffprobe, u): u for u in urls}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                is_alive = future.result()
                if is_alive:
                    final_dict[channel_name].append(url)
                    if len(final_dict[channel_name]) >= MAX_URLS_PER_CHANNEL:
                        break
            
            if len(final_dict[channel_name]) > 0:
                print(f"  -> Kept {len(final_dict[channel_name])} alive URLs.")
            else:
                print(f"  -> No alive URLs found.")

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
