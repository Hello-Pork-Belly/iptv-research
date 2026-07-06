import urllib.request
import urllib.error
import subprocess
import concurrent.futures
import time
import os

SEED_URLS = [
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    "https://0701.tv1288.xyz/",
    "https://xymm.ccwu.cc/"
]

# TARGET_CATEGORIES defines words we look for in the channel name or group to classify them.
TARGET_CHANNELS = ["CCTV", "卫视", "湖南", "凤凰", "TVB", "翡翠", "体育", "NBA", "纬来", "新闻"]

# Max URLs to keep per unique channel name to speed up scanning
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
    
    # Simple heuristic to handle both txt and m3u formats loosely
    current_name = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # M3U format
        if line.startswith("#EXTINF"):
            # Extract channel name from the end of the EXTINF line
            parts = line.split(',')
            if len(parts) > 1:
                current_name = parts[-1].strip()
        elif line.startswith("http"):
            if current_name:
                channels.append((current_name, line))
                current_name = ""
            else:
                # Might be just a URL line, fallback name
                channels.append(("Unknown", line))
        
        # TXT format (Name,URL)
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
    for target in TARGET_CHANNELS:
        if target.upper() in name_upper:
            return True
    return False

def check_url_ffprobe(url):
    """ Use ffprobe to quickly check if a stream is alive and returns video/audio data """
    # timeout is in microseconds (5 seconds = 5000000)
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "stream=codec_type", 
        "-timeout", "5000000", 
        "-i", url
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        if result.returncode == 0 and ("video" in result.stdout.decode() or "audio" in result.stdout.decode()):
            return True
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    return False

def main():
    print("Starting IPTV Scanner...")
    all_channels = []
    
    # 1. Download and aggregate all channels
    for url in SEED_URLS:
        print(f"Downloading from: {url}")
        content = download_list(url)
        parsed = parse_m3u_or_txt(content)
        all_channels.extend(parsed)
        print(f"Found {len(parsed)} streams.")
        
    # 2. Filter for Target Categories and deduplicate
    candidate_dict = {}
    for name, url in all_channels:
        if is_target_channel(name):
            # Clean name a bit
            clean_name = name.replace("高清", "").replace("1080P", "").replace("FHD", "").strip()
            if clean_name not in candidate_dict:
                candidate_dict[clean_name] = set()
            candidate_dict[clean_name].add(url)
            
    print(f"\nFiltered down to {len(candidate_dict)} unique target channels.")
    
    # 3. Validation Phase
    final_dict = {}
    
    # We will test channels concurrently. 
    # To avoid getting banned or overloading GitHub Actions, limit max workers.
    MAX_WORKERS = 10
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for channel_name, urls in candidate_dict.items():
            print(f"Testing {channel_name} (Found {len(urls)} candidates)...")
            final_dict[channel_name] = []
            
            # Submit all URL checks for this channel
            future_to_url = {executor.submit(check_url_ffprobe, u): u for u in urls}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                is_alive = future.result()
                if is_alive:
                    final_dict[channel_name].append(url)
                    if len(final_dict[channel_name]) >= MAX_URLS_PER_CHANNEL:
                        # Cancel remaining futures for this channel if we have enough
                        break
            
            print(f"  -> Kept {len(final_dict[channel_name])} alive URLs.")

    # 4. Generate Output M3U
    output_file = "best_tv.m3u"
    print(f"\nWriting results to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U x-tvg-url="https://live.fanmingming.com/e.xml"\n')
        for name, urls in final_dict.items():
            for url in urls:
                # Basic group assignment heuristic
                group = "其他"
                if "CCTV" in name.upper(): group = "央视"
                elif "卫视" in name or "湖南" in name: group = "卫视"
                elif "体育" in name or "NBA" in name: group = "体育"
                elif "TVB" in name.upper() or "翡翠" in name or "凤凰" in name or "新闻" in name: group = "港台/新闻"
                
                logo_name = name
                # Simple logo heuristic for CCTV
                import re
                cctv_match = re.search(r'CCTV[\d\+]+', name, re.IGNORECASE)
                if cctv_match: logo_name = cctv_match.group(0).upper()
                    
                logo_url = f"https://live.fanmingming.com/tv/{urllib.parse.quote(logo_name)}.png"
                
                f.write(f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n')
                f.write(f'{url}\n')

    print("Scanner finished successfully!")

if __name__ == "__main__":
    main()
