from queue import Queue
import google.generativeai as genai
from datetime import datetime
import threading
import time
from flask import Flask, render_template, jsonify, request
import requests
import re
import json
import os

app = Flask(__name__)

# Load environment variables from .env file (for local development)
try:
    with open('.env', 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                os.environ[key] = value
    print("Loaded environment variables from .env file")
except FileNotFoundError:
    print("No .env file found, assuming environment variables are set externally")

api_key = os.getenv('GEMINI_API_KEY')
unsplash_access_key = os.getenv('UNSPLASH_ACCESS_KEY')

if not api_key:
    print("ERROR: GEMINI_API_KEY not found")
if not unsplash_access_key:
    print("ERROR: UNSPLASH_ACCESS_KEY not found")

# Configure Gemini API
genai.configure(api_key=api_key)

# List available models and find the latest version
try:
    models = genai.list_models()
    available_models = [model.name for model in models]
    print("Available models:", available_models)
except Exception as e:
    print(f"Error listing models: {e}")

# Model settings
generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 8192
}

topic_queue = Queue()
latest_blog = {"content": "", "timestamp": "", "topic": ""}
processing_status = {"current_topic": None, "status": "idle"}

def fetch_images_from_unsplash(query, count=1):
    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": query.strip(),
        "per_page": count,
        "client_id": unsplash_access_key,
        "orientation": "landscape",
     }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get("results"):
            return []

        return [image["urls"]["regular"] for image in data["results"]]
    except Exception as e:
        print(f"Error fetching images: {e}")
        return []

    

def replace_image_placeholders(blog_content):
    import re
    
    placeholder_pattern = r'\[IMAGE_PLACEHOLDER:\s*([^\]]+)\]'
    placeholders = re.findall(placeholder_pattern, blog_content)
    
    if not placeholders:
        print("No image placeholders found in content")
        return blog_content
    
    modified_content = blog_content
    
    for description in placeholders:
        images = fetch_images_from_unsplash(description, count=1)
        if images:
            img_html = f'''
            <div class="blog-image-container">
                <img src="{images[0]}" 
                     alt="{description}"
                     loading="lazy" 
                     class="blog-image"
                     onerror="this.onerror=null; this.src='/static/placeholder.jpg';"
                />
            </div>
            '''
            modified_content = modified_content.replace(f'[IMAGE_PLACEHOLDER: {description}]', img_html)
        else:
            modified_content = modified_content.replace(f'[IMAGE_PLACEHOLDER: {description}]', '')
    
    return modified_content

def generate_blog(topic):
    print(f"Starting blog generation for topic: {topic}")
    long_tail_keywords = [
        f"best {topic} recommendations",
        f"top {topic} tips",
        f"complete guide to {topic}"
    ]

    short_tail_keywords = [
        topic,
        f"{topic} insights",
        f"{topic} guide"
    ]

    prompt = f"""
    Write a travel blog article about {topic} in a style of a personal travel narrative.

    Writing Guidelines:
    - Use SEO keywords is must use as many as you can .
    -Write around 3500 words and make blog in depht.
    -Break down content under SEO-friendly headings and subheadings.
    -Use ## for heading ,### for sub heading,** for bold (nothing else) .
    -write 3500 words atleast and give insights of things.
    - Follow EEAT structure to mek the blog rank high.
    1. Expert recommendations backed by data.
    2. Personal anecdotes to build trust.
    3. Local insights to demonstrate authority.
    - After every paragraph or header, include the text "[IMAGE_PLACEHOLDER: (give the name or image required)]" to indicate where an image would go.
    -Include short-tail keywords and long-tail keywords naturally within the content and headings.
    -Incorporate stats or expert data.
    - Use conversational, engaging language.
    - Create a narrative that feels authentic and personal.
    - Include specific details about locations, experiences, and emotions.
    - Provide practical travel advice seamlessly within the story.
    -Engagement Hooks:Add questions or call-to-actions like.
    -Link to reputable sources (e.g., tourism boards, maps, weather forecast sites) to build trust and authority.

    Blog Structure:(dont write words like Engaging Opening:,Journey Narrative:,Practical Tips:its for your refference write it juts like a blog is written )
    1.  Describe the initial excitement and anticipation of the trip
    2.  Detailed description of travel experiences
    3. Embed travel recommendations naturally
    4. Emotional takeaways and memorable moments

    Must Include Travel Elements:
    - Specific locations visited.
    - Local interactions.
    - Challenges and unexpected experiences.
    - Budget and planning insights.
    - Safety recommendations.

    Storytelling Tone:
    - Conversational and enthusiastic but use you more than I.
    - Mix of humor, reflection, and practical advice.

    Keywords Integration:
    Naturally weave in these keywords without forced placement:
    Long-tail keywords: {', '.join(long_tail_keywords)}
    Short-tail keywords: {', '.join(short_tail_keywords)}
    """

    try:
        max_retries = 3
        retry_delay = 45  # seconds
        
        for attempt in range(max_retries):
            try:
                # Initialize model for each generation using latest version
                model = genai.GenerativeModel('models/gemini-2.5-flash')
                
                # Generate the content
                response = model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                content = response.text
                formatted_content = format_blog_content(content)
                final_content = replace_image_placeholders(formatted_content)
                return final_content
                
            except Exception as retry_error:
                if "429" in str(retry_error) and attempt < max_retries - 1:
                    print(f"Rate limit hit, waiting {retry_delay} seconds before retry {attempt + 1}/{max_retries}")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise retry_error
        
        raise Exception("Max retries exceeded")
        
        return final_content
    except Exception as e:
        print(f"Error generating blog: {e}")
        return f"An error occurred: {e}"

def format_blog_content(raw_content):
    formatted_content = ""

 
    lines = raw_content.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("## "):
            header_text = line[3:].strip()  
            formatted_content += f"<h1>{header_text}</h1>\n"
        elif line.startswith("### "):  
            subheader_text = line[4:].strip()  
            formatted_content += f"<h2>{subheader_text}</h2>\n"
        elif "[IMAGE_PLACEHOLDER:" in line:  
            formatted_content += f"{line.replace('**', '')}\n"
        elif "**" in line:
            formatted_content += f"<p>{line.replace('**', '<b>').replace('**', '</b>')}</p>\n"
        elif "" in line:  
            bold_text = line.replace("", "<b>").replace("</b>", "")
            formatted_content += f"<p>{bold_text}</p>\n"
        elif line:  
            formatted_content += f"<p>{line}</p>\n"
        else: 
            formatted_content += "<br>\n"

    return formatted_content

def blog_generator():

    global latest_blog, processing_status
    while True:
        if not topic_queue.empty():
            topic = topic_queue.get()
            try:
                processing_status = {"current_topic": topic, "status": "processing"}
                print(f"Generating blog for topic: {topic}")
                content = generate_blog(topic)
                if content and not content.startswith("An error occurred"):
                    latest_blog = {
                        "content": content,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "topic": topic
                    }
                    processing_status = {"current_topic": None, "status": "idle"}
                    print(f"Successfully generated blog for: {topic}")
                else:
                    print(f"Failed to generate valid content for: {topic}")
                    processing_status = {"current_topic": None, "status": "error"}
            except Exception as e:
                print(f"Error in blog generator for topic {topic}: {e}")
                processing_status = {"current_topic": None, "status": "error"}
            topic_queue.task_done()
        time.sleep(5)

# Start the blog generator thread
print("Starting blog generator thread...")
threading.Thread(target=blog_generator, daemon=True).start()
print("Blog generator thread started.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_topics', methods=['POST'])
def add_topics():
   
    data = request.get_json()
    topics = data.get('topics', '').split(',')
    topics = [topic.strip() for topic in topics if topic.strip()]
    
    for topic in topics:
        topic_queue.put(topic)
    
    return jsonify({
        "message": f"Added {len(topics)} topics to queue",
        "queue_size": topic_queue.qsize()
    })

@app.route('/queue_status', methods=['GET'])
def get_queue_status():
   
    return jsonify({
        "queue_size": topic_queue.qsize(),
        "current_processing": processing_status
    })

@app.route('/latest_blog', methods=['GET'])
def get_latest_blog():
   
    return jsonify(latest_blog)

if __name__ == '__main__':
    threading.Thread(target=blog_generator, daemon=True).start()
    app.run(debug=True)
