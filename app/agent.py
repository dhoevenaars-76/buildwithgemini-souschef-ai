# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import json
import os
import re
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from dotenv import load_dotenv

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback

load_dotenv()

# Hardcode project ID and GCS bucket to avoid Agent Platform returning project number in deployed env
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-176d865cff48"
GCS_BUCKET_NAME = "souschef-ai-media-qwiklabs-gcp-02-176d865cff48"
MEMORY_BANK_ID = "8514953396543815680"

# Load Agent Engine resource name from deployment_metadata.json if available
METADATA_PATH = Path(__file__).parent.parent / "deployment_metadata.json"
remote_agent_engine_id = None
if METADATA_PATH.exists():
    try:
        with open(METADATA_PATH, "r") as f:
            metadata = json.load(f)
            remote_agent_engine_id = metadata.get("remote_agent_runtime_id")
    except Exception as e:
        print(f"Warning: Could not read deployment_metadata.json: {e}")

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=remote_agent_engine_id
)


def get_memory_service():
    """Initializes and returns the Vertex AI Memory Bank service for future redeployments."""
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """Callback triggered after each agent turn to send the session to Memory Bank for extraction, prioritizing user allergies and dietary preferences."""
    await callback_context.add_session_to_memory()
    return None


def get_firestore_client():
    """Initializes and returns a Firestore client with hardcoded project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def generate_dish_image(
    prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates an image of a dish using gemini-3.1-flash-lite-image, saves it as an artifact, uploads to Cloud Storage, and returns its public URL.

    Args:
        prompt: A description of the dish or culinary visual to generate (e.g. 'A plate of Tuscan Garlic Chicken').
        tool_context: Injected tool context for saving artifacts in ADK.

    Returns:
        The public HTTPS URL of the generated image stored in Google Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=f"High quality professional food photography of {prompt}",
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )
    except Exception as e:
        return f"Error generating image with gemini-3.1-flash-lite-image: {e}"

    if not response.candidates or not response.candidates[0].content.parts:
        return "Failed to generate image: No image content returned by model."

    image_part = None
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            image_part = part
            break

    if not image_part:
        return "Failed to generate image: No inline image bytes found in model response."

    image_bytes = image_part.inline_data.data
    mime_type = image_part.inline_data.mime_type or "image/jpeg"
    ext = "jpg" if "jpeg" in mime_type else "png"
    filename = f"dish-{uuid.uuid4().hex[:8]}.{ext}"

    # 1. Save with tool_context.save_artifact for Playground Artifacts panel
    try:
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)
    except Exception as e:
        print(f"Warning: Could not save artifact in tool_context: {e}")

    # 2. Upload same image bytes to public GCS bucket and return public URL
    try:
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)
        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"
        return f"Image generated successfully!\nPublic URL: {public_url}"
    except Exception as e:
        return f"Error uploading image to Cloud Storage: {e}"


def generate_culinary_video(
    prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates a short video for a culinary dish, recipe technique, or cooking item using Google Omni model (gemini-omni-flash-preview) in the global region.
    Saves the video with tool_context.save_artifact for the Playground's Artifacts panel, uploads it to Google Cloud Storage, and returns its public URL.

    Args:
        prompt: Description of the culinary video to generate (e.g. 'A short video showing pasta sauce simmering on a stove').
        tool_context: Injected tool context for saving artifacts in ADK.

    Returns:
        The public HTTPS URL of the generated video stored in Google Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")

    try:
        response = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"Generate a short video showing {prompt}",
        )
    except Exception as e:
        return f"Error generating video with gemini-omni-flash-preview: {e}"

    if not response or not hasattr(response, "output_video") or not response.output_video:
        return "Failed to generate video: No output_video returned from model."

    vid = response.output_video
    raw_data = getattr(vid, "data", None)
    if not raw_data:
        return "Failed to generate video: No video data returned in output_video."

    video_bytes = base64.b64decode(raw_data) if isinstance(raw_data, str) else raw_data
    mime_type = getattr(vid, "mime_type", "video/mp4") or "video/mp4"
    filename = f"cooking-{uuid.uuid4().hex[:8]}.mp4"

    # 1. Save with tool_context.save_artifact for Playground Artifacts panel
    try:
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)
    except Exception as e:
        print(f"Warning: Could not save video artifact in tool_context: {e}")

    # 2. Upload video bytes to public Cloud Storage bucket and return public URL
    try:
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)
        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"
        return f"Video generated successfully!\nPublic URL: {public_url}"
    except Exception as e:
        return f"Error uploading video to Cloud Storage: {e}"


def geocode_address(address: str) -> str:
    """Converts a street address or location name into geographic coordinates (latitude and longitude).

    Args:
        address: The address or location string to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        Formatted location details with name/address and coordinates (latitude, longitude).
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    encoded_address = urllib.parse.quote(address.strip())
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return f"Error calling Geocoding API: {e}"

    if data.get("status") != "OK" or not data.get("results"):
        return f"Could not geocode address '{address}': {data.get('status')} - {data.get('error_message', '')}"

    result = data["results"][0]
    fmt_address = result.get("formatted_address")
    location = result.get("geometry", {}).get("location", {})
    lat = location.get("lat")
    lng = location.get("lng")

    return (
        f"Geocoded Location:\n"
        f"• Address: {fmt_address}\n"
        f"• Latitude: {lat}\n"
        f"• Longitude: {lng}"
    )


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "supermarket",
    radius_meters: float = 5000.0,
) -> str:
    """Finds nearby places of a given type around coordinates using Places API (New).

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        place_type: Type of place to search for (e.g. 'supermarket', 'grocery_store', 'restaurant', 'bakery').
        radius_meters: Search radius in meters (default 5000.0).

    Returns:
        Formatted summary of nearby places with name, address, and coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius_meters,
            }
        },
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return f"Error calling Places API (New): {e}"

    places = data.get("places")
    if not places:
        return f"No nearby places found of type '{place_type}' within {radius_meters}m."

    output = []
    for p in places:
        name = p.get("displayName", {}).get("text", "Unknown")
        addr = p.get("formattedAddress", "N/A")
        loc = p.get("location", {})
        output.append(
            f"• Name: {name}\n"
            f"  Address: {addr}\n"
            f"  Location: Lat {loc.get('latitude')}, Lng {loc.get('longitude')}"
        )

    return f"Nearby '{place_type}' Places:\n\n" + "\n\n".join(output)


def search_recipes(cuisine: str = "", dietary_tag: str = "") -> str:
    """Searches recipes in the local Firestore database by cuisine or dietary tag.

    Args:
        cuisine: Optional cuisine filter (e.g. 'Italian', 'Mediterranean', 'American').
        dietary_tag: Optional dietary tag filter (e.g. 'vegan', 'keto', 'gluten-free').

    Returns:
        A list of matching recipe summaries from Firestore.
    """
    db = get_firestore_client()
    recipes_ref = db.collection("recipes")
    docs = recipes_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        if cuisine and cuisine.lower() not in data.get("cuisine", "").lower():
            continue
        if dietary_tag:
            tags = [t.lower() for t in data.get("dietary_tags", [])]
            if dietary_tag.lower() not in tags:
                continue
        results.append(data)

    if not results:
        return f"No recipes found in local database matching cuisine='{cuisine}' and dietary_tag='{dietary_tag}'."

    output = []
    for r in results:
        output.append(
            f"• {r.get('title')} ({r.get('cuisine')}) - Prep: {r.get('prep_time_minutes')}m, Cook: {r.get('cook_time_minutes')}m, Servings: {r.get('servings')}\n"
            f"  Tags: {', '.join(r.get('dietary_tags', []))}\n"
            f"  Ingredients: {', '.join(r.get('ingredients', []))}\n"
            f"  Instructions: {' '.join(r.get('instructions', []))}"
        )
    return "\n\n".join(output)


def search_online_recipes(query: str) -> str:
    """Searches the online recipe database (TheMealDB) for real global recipes.

    Args:
        query: Name of the dish, cuisine, or key ingredient to search for online (e.g. 'Penne', 'Tacos', 'Curry').

    Returns:
        Formatted summary of online recipe results including ingredients, instructions, and image URL.
    """
    api_key = os.environ.get("THEMEALDB_API_KEY", "1")
    encoded_query = urllib.parse.quote(query.strip())
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={encoded_query}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SousChefAI/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return f"Error fetching online recipes from TheMealDB: {e}"

    meals = data.get("meals")
    if not meals:
        return f"No online recipes found matching query '{query}'."

    results = []
    for m in meals[:3]:  # Top 3 results
        ingredients = []
        for i in range(1, 21):
            ing = m.get(f"strIngredient{i}")
            meas = m.get(f"strMeasure{i}")
            if ing and ing.strip():
                measure_str = f" ({meas.strip()})" if meas and meas.strip() else ""
                ingredients.append(f"{ing.strip()}{measure_str}")

        instructions = m.get("strInstructions", "").replace("\r\n", " ")
        if len(instructions) > 300:
            instructions = instructions[:297] + "..."

        results.append(
            f"• {m.get('strMeal')} ({m.get('strArea', 'International')} {m.get('strCategory', '')})\n"
            f"  Ingredients: {', '.join(ingredients)}\n"
            f"  Instructions: {instructions}\n"
            f"  Image URL: {m.get('strMealThumb')}"
        )

    return "\n\n".join(results)


def add_recipe(
    title: str,
    cuisine: str,
    prep_time_minutes: int,
    cook_time_minutes: int,
    servings: int,
    dietary_tags: list[str],
    ingredients: list[str],
    instructions: list[str],
) -> str:
    """Adds a new recipe to the local Firestore recipes collection.

    Args:
        title: Title of the recipe.
        cuisine: Cuisine category (e.g., Italian, Mexican, Asian).
        prep_time_minutes: Preparation time in minutes.
        cook_time_minutes: Cooking time in minutes.
        servings: Number of servings.
        dietary_tags: List of dietary tags (e.g., ['vegan', 'gluten-free']).
        ingredients: List of ingredient strings.
        instructions: Step-by-step cooking instructions.

    Returns:
        Confirmation message with document ID.
    """
    db = get_firestore_client()
    doc_id = title.lower().replace(" ", "-")
    doc_ref = db.collection("recipes").document(doc_id)

    recipe_data = {
        "id": doc_id,
        "title": title,
        "cuisine": cuisine,
        "prep_time_minutes": prep_time_minutes,
        "cook_time_minutes": cook_time_minutes,
        "servings": servings,
        "dietary_tags": dietary_tags,
        "ingredients": ingredients,
        "instructions": instructions,
    }
    doc_ref.set(recipe_data)
    return f"Successfully added recipe '{title}' to Firestore with ID '{doc_id}'."


def scale_recipe_servings(recipe_title: str, target_servings: int) -> str:
    """Scales a recipe's ingredient quantities from its base servings to target_servings.

    Args:
        recipe_title: Title or name of the recipe in Firestore.
        target_servings: Desired number of servings to scale to.

    Returns:
        Formatted ingredient list with scaled quantities.
    """
    db = get_firestore_client()
    recipes_ref = db.collection("recipes")
    docs = recipes_ref.stream()

    match = None
    for doc in docs:
        data = doc.to_dict()
        if recipe_title.lower() in data.get("title", "").lower() or data.get("id") == recipe_title:
            match = data
            break

    if not match:
        return f"Recipe matching '{recipe_title}' not found in catalog."

    base_servings = match.get("servings", 1) or 1
    scale_factor = target_servings / base_servings

    scaled_ingredients = []
    for ing in match.get("ingredients", []):
        m = re.match(r"^(\d+/\d+|\d+(?:\.\d+)?)\s*(.*)", ing.strip())
        if m:
            raw_qty = m.group(1)
            rest = m.group(2)
            if "/" in raw_qty:
                parts = raw_qty.split("/")
                qty = (float(parts[0]) / float(parts[1])) * scale_factor
            else:
                qty = float(raw_qty) * scale_factor
            scaled_num = f"{qty:.2f}".rstrip("0").rstrip(".")
            scaled_ingredients.append(f"• {scaled_num} {rest}")
        else:
            scaled_ingredients.append(f"• {ing} (scaled x{scale_factor:.2f})")

    return (
        f"Scaled '{match.get('title')}' for {target_servings} servings "
        f"(Base: {base_servings} servings, Scale Factor: {scale_factor:.2f}x):\n"
        + "\n".join(scaled_ingredients)
    )


def get_pantry_inventory() -> str:
    """Retrieves all current pantry items stored in Firestore.

    Returns:
        Formatted summary of items in the pantry.
    """
    db = get_firestore_client()
    pantry_ref = db.collection("pantry")
    docs = pantry_ref.stream()

    items = [doc.to_dict() for doc in docs]
    if not items:
        return "Your pantry is currently empty."

    formatted = [f"• {item.get('item_name')} ({item.get('category')}): {item.get('quantity')}" for item in items]
    return "Current Pantry Inventory:\n" + "\n".join(formatted)


def add_pantry_item(item_name: str, category: str, quantity: str) -> str:
    """Adds or updates an item in the Firestore pantry collection.

    Args:
        item_name: Name of the pantry item (e.g. 'Olive Oil', 'Garlic').
        category: Category of the item (e.g. 'Produce', 'Spices', 'Dairy').
        quantity: Quantity string (e.g. '2 lbs', '1 bottle').

    Returns:
        Confirmation message.
    """
    db = get_firestore_client()
    doc_id = item_name.lower().replace(" ", "-")
    doc_ref = db.collection("pantry").document(doc_id)

    item_data = {
        "id": doc_id,
        "item_name": item_name,
        "category": category,
        "quantity": quantity,
    }
    doc_ref.set(item_data)
    return f"Successfully updated pantry item '{item_name}' ({quantity}) in Firestore."


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="You are SousChef AI, a world-class personal chef and culinary assistant.",
    workflow_description="Analyze the user request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

domain_instruction = (
    "CRITICAL RULE: You must carefully remember and prioritize ALL user food allergies, dietary restrictions, "
    "and health sensitivities (e.g. peanuts, gluten, dairy, shellfish) across sessions. "
    "Whenever a user states an allergy, make sure it is noted and stored in long-term memory. "
    "Always cross-reference preloaded user memories before recommending any recipe, meal, or ingredient. "
    "You help users search local Firestore recipes, search online recipes via TheMealDB API, "
    "generate food photography images using generate_dish_image, "
    "generate short video clips of dishes or cooking techniques using generate_culinary_video, "
    "geocode addresses, find nearby supermarkets/grocery stores using Google Maps & Places API (New), "
    "scale recipes, and manage pantry items. "
    "You have a code execution sandbox for running Python code to compute complex math or calculations when needed. "
    "Always use your tools when requested."
)

instruction = f"{a2ui_instruction}\n\n{domain_instruction}"

root_agent = Agent(
    name="souschef_ai",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        generate_dish_image,
        generate_culinary_video,
        geocode_address,
        find_nearby_places,
        search_recipes,
        search_online_recipes,
        add_recipe,
        scale_recipe_servings,
        get_pantry_inventory,
        add_pantry_item,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="souschef_ai",
)
