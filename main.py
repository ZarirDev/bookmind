from scraper import get_class_links, scrape_download_links

# Get cached class list (no website hit unless cache expired)
classes = get_class_links()
print(f"Found {len(classes)} classes")

# Force a fresh fetch (ignore cache)
fresh = get_class_links(force_refresh=True)

print(classes)

# Scrape English version of the first class page
# if classes:
#     sample_url = classes[0][1]
#     books = scrape_download_links(sample_url, language='english')
#     print(books)