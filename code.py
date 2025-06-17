import os
import re
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def fetch_m3u_content(url):
    """Fetches the M3U content from the given URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching M3U content from {url}: {e}")
        return None

def parse_m3u(content):
    """Parses M3U content into a list of dictionaries."""
    channels = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            channel_info = {}
            # Extract attributes from #EXTINF line
            match = re.search(r'tvg-id="([^"]*)"', line)
            if match: channel_info['tvg-id'] = match.group(1)
            match = re.search(r'tvg-name="([^"]*)"', line)
            if match: channel_info['tvg-name'] = match.group(1)
            match = re.search(r'tvg-logo="([^"]*)"', line)
            if match: channel_info['tvg-logo'] = match.group(1)
            match = re.search(r'group-title="([^"]*)"', line)
            if match: channel_info['group-title'] = match.group(1)

            # Extract channel name (the part after #EXTINF attributes)
            name_match = re.search(r',(.+)$', line)
            if name_match:
                channel_info['name'] = name_match.group(1).strip()
            else:
                channel_info['name'] = "Unknown Channel"

            # Check next line for URL
            if i + 1 < len(lines):
                url_line = lines[i+1].strip()
                if not url_line.startswith('#'): # Ensure it's not another EXTINF or comment
                    channel_info['url'] = url_line
                    channels.append(channel_info)
                    i += 1 # Move to URL line, next iteration will go to next EXTINF
            else:
                # If there's no URL after EXTINF, it's an incomplete entry
                pass # Or add to channels with missing URL, depending on desired behavior
        i += 1
    return channels

def filter_and_categorize_channels(channels, desired_keywords, category_map):
    """
    Filters channels based on desired keywords and assigns them to categories.

    Args:
        channels (list): List of channel dictionaries.
        desired_keywords (list): List of keywords (case-insensitive) to look for in channel name or group-title.
        category_map (dict): A dictionary where keys are category names and values are
                              lists of keywords that define that category.
    Returns:
        list: A list of filtered and categorized channel dictionaries.
    """
    filtered_channels = []
    for channel in channels:
        channel_name = channel.get('name', '').lower()
        group_title = channel.get('group-title', '').lower()
        original_group_title = channel.get('group-title', '') # Keep original for default if no new category found

        # Filter by desired keywords
        is_desired = False
        for keyword in desired_keywords:
            if keyword.lower() in channel_name or keyword.lower() in group_title:
                is_desired = True
                break

        if is_desired:
            # Assign category based on category_map
            assigned_category = "Other" # Default category
            for category_name, category_keywords in category_map.items():
                for cat_keyword in category_keywords:
                    # Check if the channel name or original group title contains the category keyword
                    if cat_keyword.lower() in channel_name or cat_keyword.lower() in original_group_title:
                        assigned_category = category_name
                        break
                if assigned_category != "Other":
                    break # Found a category, move to next channel

            channel['group-title'] = assigned_category # Update the group-title for output
            filtered_channels.append(channel)
    return filtered_channels

def generate_m3u_output(channels, output_filename="list.m3u"):
    """Generates an M3U file from the filtered and categorized channels."""
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n') # M3U header
            for channel in channels:
                extinf_line = '#EXTINF:-1'
                if 'tvg-id' in channel: extinf_line += f' tvg-id="{channel["tvg-id"]}"'
                if 'tvg-name' in channel: extinf_line += f' tvg-name="{channel["tvg-name"]}"'
                if 'tvg-logo' in channel: extinf_line += f' tvg-logo="{channel["tvg-logo"]}"'
                if 'group-title' in channel: extinf_line += f' group-title="{channel["group-title"]}"'
                extinf_line += f',{channel.get("name", "Unknown")}\n'
                f.write(extinf_line)
                f.write(f'{channel.get("url", "")}\n')
        print(f"Successfully generated {output_filename}")
    except IOError as e:
        print(f"Error writing to file {output_filename}: {e}")

def main():
    m3u_url = os.getenv('M3U_URL')

    if not m3u_url:
        print("Error: M3U_URL not found in .env file. Please create a .env file and add M3U_URL='your_m3u_url_here'")
        return

    # --- USER CONFIGURATION ---
    # Define how you want to categorize your channels.
    # Keys are your desired category names (e.g., "Bollywood Movies"),
    # values are lists of keywords that will place a channel into that category.
    # Channels are categorized based on their name or original group-title.
    category_map = {
        "Entertainment": [
            "Star Plus", "Star Bharat", "Sony TV", "Sony SAB", "Colors TV", "Zee TV", "Zee Anmol", "Sony Pal", "& TV",
            "Star Utsav" # Added a common entertainment channel for completeness
        ],
        "Movies": [
            "Star Gold", "Star Gold Select", "Zee Cinema", "Zee Action", "Zee Bollywood", "Zee Classic",
            "Sony Max", "Sony Max 2", "Sony Wah", "Colors Cineplex", "& pictures", "UTV Movies", "UTV Action", "B4U Movies", "Zee Anmol Cinema",
            "Cinema" # Generic keyword for movies
        ],
        "Kids": [
            "Cartoon Network", "Pogo", "Hungama TV", "Disney Channel", "Nick", "Nick HD+", "Discovery Kids",
            "Chutti TV" # Another common kids channel
        ],
        "Knowledge": [
            "Discovery Channel", "Discovery Science", "National Geographic", "History TV18", "Animal Planet",
            "Docu" # Generic keyword for documentaries/knowledge
        ],
        "Sports": [
            "Star Sports", "Sony Ten", "Sony Six", "Sony Ten 1", "Sony Ten 2", "Sony Ten 3", "Sony Ten 4", "Sports18",
            "Sport", "IPL" # Generic keywords for sports
        ]
    }

    # Automatically generate desired_keywords from all keywords in category_map
    desired_keywords = []
    for keywords_list in category_map.values():
        desired_keywords.extend(keywords_list)
    # Add any additional general keywords you might want to include that aren't specific to a category
    desired_keywords.extend(["HD", "Live", "English", "Hindi", "Regional News"])
    # Remove duplicates
    desired_keywords = list(set(desired_keywords))

    # --- END USER CONFIGURATION ---

    print(f"Fetching M3U content from: {m3u_url}")
    m3u_content = fetch_m3u_content(m3u_url)

    if m3u_content:
        print("Parsing M3U content...")
        channels = parse_m3u(m3u_content)
        print(f"Found {len(channels)} channels in the raw M3U file.")

        print("Filtering and categorizing channels...")
        filtered_and_categorized_channels = filter_and_categorize_channels(
            channels, desired_keywords, category_map
        )
        print(f"Found {len(filtered_and_categorized_channels)} desired and categorized channels.")

        # Sort channels by their new group-title and then by name for better organization
        filtered_and_categorized_channels.sort(key=lambda x: (x.get('group-title', ''), x.get('name', '')))

        print("Generating list.m3u file...")
        generate_m3u_output(filtered_and_categorized_channels)
    else:
        print("Failed to fetch M3U content. Exiting.")

if __name__ == "__main__":
    main()
