import os
import re
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def fetch_m3u_content(url):
    """
    Fetches the M3U content from the given URL.
    Includes a timeout and error handling for network requests.
    """
    print(f"Attempting to fetch M3U content from: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        print("Successfully fetched M3U content.")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching M3U content: {e}")
        return None

def parse_m3u(content):
    """
    Parses M3U content into a list of dictionaries.
    Each dictionary represents a channel with its attributes (tvg-id, group-title, etc.) and URL.
    Handles potential missing URLs or malformed entries more gracefully.
    """
    channels = []
    lines = content.splitlines()
    i = 0
    print("Starting M3U content parsing...")
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            channel_info = {}
            # Extract attributes using regex.
            attributes = re.findall(r'(\S+?)="([^"]*)"', line)
            for attr_key, attr_value in attributes:
                channel_info[attr_key.replace('-', '_')] = attr_value

            # Extract channel name (the part after #EXTINF attributes and the last comma)
            name_match = re.search(r',(.+)$', line)
            channel_info['name'] = name_match.group(1).strip() if name_match else "Unknown Channel"

            # Check the next line for the channel URL.
            if i + 1 < len(lines) and not lines[i+1].strip().startswith('#'):
                channel_info['url'] = lines[i+1].strip()
                channels.append(channel_info)
                i += 1 # Increment to skip the URL line on the next iteration
            else:
                print(f"  Warning: Skipping channel '{channel_info.get('name', 'Unknown')}' due to missing or invalid URL line.")
        i += 1
    print(f"Finished parsing. Found {len(channels)} potential channels.")
    return channels

def filter_and_categorize_by_category_map(channels, category_map, vod_blacklist_keywords):
    """
    Filters channels:
    1. Excludes VOD/non-live content using a blacklist.
    2. Includes ONLY channels that match keywords within the provided category_map.
    Assigns matched channels to their respective categories based on the first match.

    Args:
        channels (list): List of channel dictionaries from parsing.
        category_map (dict): Maps desired category names to lists of keywords. This also defines inclusion.
        vod_blacklist_keywords (list): Keywords (case-insensitive) to explicitly exclude VOD/non-live channels.

    Returns:
        list: A list of filtered and categorized channel dictionaries.
    """
    filtered_channels = []
    print("Starting filtering and categorization based on category map...")

    # Pre-process blacklist keywords for efficient lookup
    vod_blacklist_keywords_lower = {k.lower() for k in vod_blacklist_keywords}

    # Prepare category map for efficient lookup and matching
    # Stores {category_name: set_of_lowercase_keywords}
    processed_category_map = {
        name: {kw.lower() for kw in kws}
        for name, kws in category_map.items()
    }

    for channel in channels:
        channel_name_lower = channel.get('name', '').lower()
        original_group_title_lower = channel.get('group_title', '').lower()

        # --- Step 1: Exclude VOD/Non-Live Content ---
        is_vod = False
        for vod_keyword in vod_blacklist_keywords_lower:
            # Use word boundaries for more precise matching (e.g., "vod" matches "vod" but not "devod")
            if re.search(r'\b' + re.escape(vod_keyword) + r'\b', channel_name_lower) or \
               re.search(r'\b' + re.escape(vod_keyword) + r'\b', original_group_title_lower):
                is_vod = True
                break
        if is_vod:
            # print(f"  Skipping (VOD/Non-Live): {channel_name_lower}") # For debugging
            continue # Skip this channel if it matches a VOD blacklist keyword

        # --- Step 2: Include and Categorize based on Category Map ---
        assigned_category = None
        for category_name, category_keywords_set in processed_category_map.items():
            for cat_keyword in category_keywords_set:
                # If channel name OR its original group title contains the category keyword
                if re.search(r'\b' + re.escape(cat_keyword) + r'\b', channel_name_lower) or \
                   re.search(r'\b' + re.escape(cat_keyword) + r'\b', original_group_title_lower):
                    assigned_category = category_name
                    break # Found a category, stop checking keywords for this category
            if assigned_category:
                break # Found a category for this channel, stop checking other categories

        if assigned_category:
            channel['group_title'] = assigned_category # Update the group-title for output
            filtered_channels.append(channel)
        # else:
            # print(f"  Skipping (No category match): {channel_name_lower}") # For debugging

    print(f"Finished filtering and categorization. {len(filtered_channels)} channels will be written.")
    return filtered_channels

def generate_m3u_output(channels, output_filename="list.m3u"):
    """
    Generates an M3U file from the filtered and categorized channel data.
    Ensures all relevant M3U attributes are written back correctly.
    """
    print(f"Generating output M3U file: {output_filename}")
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n') # M3U header is mandatory
            for channel in channels:
                extinf_line = '#EXTINF:-1' # Default -1 for duration

                # Dynamically add all recognized EXTINF attributes
                for attr_key_py, attr_val in channel.items():
                    # Only include attributes that are typically part of EXTINF and not the name/url itself
                    if attr_key_py in ['tvg_id', 'tvg_name', 'tvg_logo', 'group_title', 'tvg_url', 'tvg_rec', 'tvg_shift']:
                        extinf_line += f' {attr_key_py.replace("_", "-")}="{attr_val}"'

                # Add the channel name after the last comma
                extinf_line += f',{channel.get("name", "Unknown Channel")}\n'
                f.write(extinf_line)
                # Write the URL on the next line
                f.write(f'{channel.get("url", "")}\n')
        print(f"Successfully generated {output_filename}")
    except IOError as e:
        print(f"Error writing to file {output_filename}: {e}")

def main():
    m3u_url = os.getenv('M3U_URL')

    if not m3u_url:
        print("\nError: M3U_URL environment variable not found.")
        print("Please create a .env file in the same directory as the script with the following content:")
        print("M3U_URL=\"http://your-m3u-playlist-url.com/playlist.m3u\"")
        print("Exiting.")
        return

    # --- USER CONFIGURATION START ---

    # *** THIS IS THE ONLY PRIMARY INPUT FOR FILTERING AND CATEGORIZATION ***
    # Define your desired categories and the keywords that define them.
    # A channel will be INCLUDED in the output ONLY if its name or original group-title
    # matches at least one keyword in ANY of these categories.
    # The channel's 'group-title' in the output will be set to the first matching category name.
    # Matching is case-insensitive and uses word boundaries for precision.
    category_map = {
        "My Entertainment": [
            "Star Plus", "Sony TV", "Colors TV", "& TV", "Star Utsav",
            "Zee TV", "Sony SAB", "Star Bharat", "Zee Anmol", "Sony Pal"
        ],
        "My Movies": [
            "Zee Cinema", "Star Gold", "Sony Max", "Colors Cineplex", "UTV Movies", "& pictures", "B4U Movies",
            "Zee Bollywood", "Zee Action", "Zee Classic", "Sony Max 2", "Sony Wah", "Zee Anmol Cinema"
        ],
        "My Kids Shows": [
            "Cartoon Network", "Pogo", "Hungama TV", "Disney Channel", "Nick", "Nick HD+", "Discovery Kids"
        ],
        "My Knowledge": [
            "Discovery Channel", "National Geographic", "History TV18", "Animal Planet"
        ],
        "My Sports": [
            "Star Sports", "Sony Ten", "Sports18"
        ],
        "My News": [
            "Aaj Tak", "BBC News", "NDTV", "Zee News", "ABP News", "Republic TV"
        ]
        # Add more custom categories and their defining keywords here.
        # Channels not matching any category will be EXCLUDED.
    }

    # Optional: Keywords to explicitly exclude non-live content (e.g., VOD, series libraries).
    # These terms are checked FIRST. If a channel contains any of these, it's immediately excluded,
    # regardless of whether it matches a category keyword.
    vod_blacklist_keywords = [
        "VOD", "Series", "Movies Library", "Movie Library", "Archives", "Box Office", "Replay", "On Demand",
        "Recordings", "Recorded", "Catchup", "EPG", "Season", "Episode",
        # Refine this list based on your specific M3U content to avoid excluding live channels.
    ]

    # --- USER CONFIGURATION END ---

    print("\n--- M3U Processor Started ---")
    print(f"Configured M3U URL: {m3u_url}")
    print(f"Number of categories defined: {len(category_map)}")
    print(f"Number of VOD blacklist keywords: {len(vod_blacklist_keywords)}")


    m3u_content = fetch_m3u_content(m3u_url)

    if m3u_content:
        channels = parse_m3u(m3u_content)

        print("\nApplying filters and categorizing based on single category map input...")
        filtered_and_categorized_channels = filter_and_categorize_by_category_map(
            channels, category_map, vod_blacklist_keywords
        )
        print(f"Final count of channels after filtering and categorization: {len(filtered_and_categorized_channels)}")

        # Sort channels for a clean output M3U file: first by new group-title, then by channel name.
        filtered_and_categorized_channels.sort(key=lambda x: (x.get('group_title', 'ZZZ_Unknown_Category'), x.get('name', 'ZZZ_Unknown_Channel')))

        generate_m3u_output(filtered_and_categorized_channels)
        print("\n--- M3U Processor Finished Successfully ---")
    else:
        print("\nFailed to retrieve M3U content. Please check the URL and your internet connection.")
        print("--- M3U Processor Finished with Errors ---")

if __name__ == "__main__":
    main()
