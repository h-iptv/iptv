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
        # Added a timeout of 10 seconds to prevent indefinite waiting
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
            # tvg-id="abc" -> {'tvg-id': 'abc'}
            attributes = re.findall(r'(\S+?)="([^"]*)"', line)
            for attr_key, attr_value in attributes:
                # Store attribute keys with underscores for easier Python access (e.g., tvg_id)
                channel_info[attr_key.replace('-', '_')] = attr_value

            # Extract channel name (the part after #EXTINF attributes and the last comma)
            name_match = re.search(r',(.+)$', line)
            channel_info['name'] = name_match.group(1).strip() if name_match else "Unknown Channel"

            # Check the next line for the channel URL.
            # It must not be another #EXTINF tag or a comment.
            if i + 1 < len(lines) and not lines[i+1].strip().startswith('#'):
                channel_info['url'] = lines[i+1].strip()
                channels.append(channel_info)
                i += 1 # Increment to skip the URL line on the next iteration
            else:
                # If no valid URL line found, print a warning and skip this channel entry
                print(f"  Warning: Skipping channel '{channel_info.get('name', 'Unknown')}' due to missing or invalid URL line.")
        i += 1
    print(f"Finished parsing. Found {len(channels)} potential channels.")
    return channels

def filter_and_categorize_channels(channels, desired_keywords, category_map, vod_blacklist_keywords):
    """
    Filters channels based on:
    1. Exclusion of VOD/non-live content using a blacklist.
    2. Inclusion based on desired keywords (for identifying "live TV").
    Then assigns remaining channels to specified categories.

    Args:
        channels (list): List of channel dictionaries from parsing.
        desired_keywords (list): Keywords (case-insensitive) to include channels (e.g., "Live", category names).
        category_map (dict): Maps desired category names to lists of keywords.
        vod_blacklist_keywords (list): Keywords (case-insensitive) to exclude VOD/non-live channels.

    Returns:
        list: A list of filtered and categorized live TV channel dictionaries.
    """
    filtered_channels = []
    print("Starting filtering and categorization...")

    # Convert all keywords to lowercase sets for efficient lookup
    desired_keywords_lower = {k.lower() for k in desired_keywords}
    vod_blacklist_keywords_lower = {k.lower() for k in vod_blacklist_keywords}

    for channel in channels:
        channel_name_lower = channel.get('name', '').lower()
        group_title_lower = channel.get('group_title', '').lower() # Use group_title as parsed with underscore

        # --- Live TV Filtering: Step 1 - Exclude VOD/Non-Live Content ---
        is_vod = False
        for vod_keyword in vod_blacklist_keywords_lower:
            # Using re.search with word boundaries for more precise matching
            # e.g., "vod" won't match "devod" but will match "vod" or "vod channel"
            if re.search(r'\b' + re.escape(vod_keyword) + r'\b', channel_name_lower) or \
               re.search(r'\b' + re.escape(vod_keyword) + r'\b', group_title_lower):
                is_vod = True
                break
        if is_vod:
            # print(f"  Skipping (VOD/Non-Live): {channel_name_lower}") # For debugging
            continue # Skip this channel if it matches a VOD blacklist keyword

        # --- Live TV Filtering: Step 2 - Include based on Desired Live TV Keywords ---
        is_desired_live_tv = False
        for desired_keyword in desired_keywords_lower:
            # Again, using word boundaries for precision
            if re.search(r'\b' + re.escape(desired_keyword) + r'\b', channel_name_lower) or \
               re.search(r'\b' + re.escape(desired_keyword) + r'\b', group_title_lower):
                is_desired_live_tv = True
                break
        if not is_desired_live_tv:
            # print(f"  Skipping (Not desired live TV): {channel_name_lower}") # For debugging
            continue # Skip if it doesn't match any desired live TV keyword

        # --- Categorization of remaining Live TV Channels ---
        assigned_category = "Other Live TV" # Default category for desired live channels not explicitly mapped
        original_group_title_for_categorization = channel.get('group_title', '') # Use original for mapping

        found_category = False
        for category_name, category_keywords in category_map.items():
            category_keywords_lower = {k.lower() for k in category_keywords} # Convert to lower for efficient check
            for cat_keyword in category_keywords_lower:
                if re.search(r'\b' + re.escape(cat_keyword) + r'\b', channel_name_lower) or \
                   re.search(r'\b' + re.escape(cat_keyword) + r'\b', original_group_title_for_categorization.lower()):
                    assigned_category = category_name
                    found_category = True
                    break
            if found_category:
                break # Found a category for this channel, no need to check other categories

        # Update the group-title attribute for the output M3U file
        channel['group_title'] = assigned_category
        filtered_channels.append(channel)

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
                    if attr_key_py in ['tvg_id', 'tvg_name', 'tvg_logo', 'group_title', 'tvg_url', 'tvg_rec']:
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

    # Define your desired categories and the keywords that define them.
    # Channels will be assigned to the first category whose keywords they match.
    # Case-insensitive matching is performed.
    category_map = {
        "Entertainment": [
            "Star Plus", "Star Bharat", "Sony TV", "Sony SAB", "Colors TV", "Zee TV", "Zee Anmol", "Sony Pal", "& TV",
            "Star Utsav"
        ],
        "Movies": [
            "Star Gold", "Star Gold Select", "Zee Cinema", "Zee Action", "Zee Bollywood", "Zee Classic",
            "Sony Max", "Sony Max 2", "Sony Wah", "Colors Cineplex", "& pictures", "UTV Movies", "UTV Action", "B4U Movies", "Zee Anmol Cinema"
        ],
        "Kids": [
            "Cartoon Network", "Pogo", "Hungama TV", "Disney Channel", "Nick", "Nick HD+", "Discovery Kids",
            "Chutti TV", "Kids", "Children", "Júnior", "Animation", "Toons"
        ],
        "Knowledge & Documentaries": [ # Renamed for clarity
            "Discovery Channel", "Discovery Science", "National Geographic", "History TV18", "Animal Planet",
            "Knowledge"
        ],
        "Sports": [
            "Star Sports", "Sony Ten", "Sony Six", "Sony Ten 1", "Sony Ten 2", "Sony Ten 3", "Sony Ten 4", "Sports18", "IPL"
        ],
        "News": [
            "India News", "World News", "BBC News", "NDTV", "Aaj Tak", "Zee News",
            "Republic TV", "ABP News",
        # Add more categories as needed
    }

    # Keywords to explicitly exclude non-live content (e.g., VOD, series libraries, movies that are not live channels)
    # These terms are checked first. If a channel contains any of these, it's immediately excluded.
    vod_blacklist_keywords = [
        "VOD", "Series", "Movies Library", "Movie Library", "Archives", "Box Office", "Replay", "On Demand",
        "Recordings", "Recorded", "Catchup", "EPG", "Season", "Episode",
        # Ensure these are distinct from actual live movie channels (e.g., "Zee Cinema Live" vs "Zee Cinema Movies Library")
        # You might need to refine this list based on your specific M3U content.
    ]

    # Automatically generate `desired_keywords` from all keywords in `category_map`.
    # This ensures that any channel you've explicitly listed in your categories is considered "desired".
    desired_keywords = []
    for keywords_list in category_map.values():
        desired_keywords.extend(keywords_list)

    # Add general keywords that strongly indicate "live TV" content.
    # These are crucial for the "only fetch live tv channels" requirement.
    desired_keywords.extend([
        "Live", "HD", "TV", "Channel", "Stream", "24/7", "news", "sports", "entertainment", "kids", "music",
        # Be careful not to make this list too broad if you want very strict filtering.
        # Channels must contain *at least one* of these keywords (or those from categories) to be included.
    ])
    # Remove duplicates and convert all to lowercase for consistent matching
    desired_keywords = list(set([k.lower() for k in desired_keywords]))

    # --- USER CONFIGURATION END ---

    print("\n--- M3U Processor Started ---")
    print(f"Configured M3U URL: {m3u_url}")
    print(f"Number of desired keywords: {len(desired_keywords)}")
    print(f"Number of VOD blacklist keywords: {len(vod_blacklist_keywords)}")

    m3u_content = fetch_m3u_content(m3u_url)

    if m3u_content:
        channels = parse_m3u(m3u_content)

        print("\nApplying filters and categorizing...")
        filtered_and_categorized_channels = filter_and_categorize_channels(
            channels, desired_keywords, category_map, vod_blacklist_keywords
        )
        print(f"Final count of live TV channels after filtering and categorization: {len(filtered_and_categorized_channels)}")

        # Sort channels for a clean output M3U file: first by new group-title, then by channel name.
        filtered_and_categorized_channels.sort(key=lambda x: (x.get('group_title', 'ZZZ_Unknown_Category'), x.get('name', 'ZZZ_Unknown_Channel')))

        generate_m3u_output(filtered_and_categorized_channels)
        print("\n--- M3U Processor Finished Successfully ---")
    else:
        print("\nFailed to retrieve M3U content. Please check the URL and your internet connection.")
        print("--- M3U Processor Finished with Errors ---")

if __name__ == "__main__":
    main()
