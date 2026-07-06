import urllib.request
import urllib.parse
import os

SEED_URLS = [
    "https://0701.tv1288.xyz/",
    "https://xymm.ccwu.cc/"
]

TARGET_CHANNELS = ["CCTV", "卫视", "湖南", "凤凰", "TVB", "翡翠", "体育", "NBA", "新闻"]

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
        
        # M3U format
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

def main():
    print("Starting IPTV Scanner (Premium Seeds Only)...")
    
    # We use a dictionary where key is channel name, value is list of URLs.
    # This preserves the order: URLs from the first seed (0701) will be added before the second (xymm).
    final_dict = {}
    
    for url in SEED_URLS:
        print(f"Downloading from: {url}")
        content = download_list(url)
        parsed = parse_m3u_or_txt(content)
        print(f"Found {len(parsed)} streams.")
        
        for name, stream_url in parsed:
            if is_target_channel(name):
                # Clean name for grouping
                clean_name = name.replace("高清", "").replace("1080P", "").replace("FHD", "").replace("+", "").strip()
                if clean_name not in final_dict:
                    final_dict[clean_name] = []
                # Avoid exact duplicates
                if stream_url not in final_dict[clean_name]:
                    final_dict[clean_name].append(stream_url)
    
    print(f"\nExtracted {len(final_dict)} unique target channels.")
    
    output_file = "best_tv.m3u"
    print(f"\nWriting results to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U x-tvg-url="https://live.fanmingming.com/e.xml"\n')
        for name, urls in final_dict.items():
            for url in urls:
                group = "其他"
                if "CCTV" in name.upper(): group = "央视"
                elif "卫视" in name or "湖南" in name: group = "卫视"
                elif "体育" in name or "NBA" in name: group = "体育"
                elif "TVB" in name.upper() or "翡翠" in name or "凤凰" in name or "新闻" in name: group = "港台新闻"
                
                logo_name = name
                import re
                cctv_match = re.search(r'CCTV[\d\+]+', name, re.IGNORECASE)
                if cctv_match: logo_name = cctv_match.group(0).upper()
                    
                logo_url = f"https://live.fanmingming.com/tv/{urllib.parse.quote(logo_name)}.png"
                
                f.write(f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo_url}" group-title="{group}",{name}\n')
                f.write(f'{url}\n')

    print("Scanner finished successfully!")

if __name__ == "__main__":
    main()
