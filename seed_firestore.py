"""Seed Firestore database with initial recipe and pantry items for SousChef AI."""

import google.auth
from google.cloud import firestore

# Hardcode Project ID to avoid Agent Platform returning project number
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-176d865cff48"


def seed_database():
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/datastore"]
    )
    db = firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials)

    # Seed recipes collection
    recipes_ref = db.collection("recipes")
    initial_recipes = [
        {
            "id": "tuscan-garlic-chicken",
            "title": "Tuscan Garlic Chicken",
            "cuisine": "Italian",
            "prep_time_minutes": 15,
            "cook_time_minutes": 25,
            "servings": 4,
            "dietary_tags": ["keto", "low-carb", "gluten-free"],
            "ingredients": [
                "1.5 lbs chicken breast",
                "1 cup heavy cream",
                "1/2 cup sun-dried tomatoes",
                "2 cups spinach",
                "4 cloves garlic, minced",
                "2 tbsp olive oil",
            ],
            "instructions": [
                "Season chicken breasts with salt and pepper.",
                "Sear chicken in olive oil for 6-8 minutes per side until cooked through.",
                "Remove chicken and sauté minced garlic and sun-dried tomatoes in the pan.",
                "Pour in heavy cream and bring to a gentle simmer.",
                "Stir in spinach until wilted, return chicken to the pan, and serve warm.",
            ],
        },
        {
            "id": "creamy-tomato-basil-soup",
            "title": "Creamy Tomato Basil Soup",
            "cuisine": "American",
            "prep_time_minutes": 10,
            "cook_time_minutes": 20,
            "servings": 4,
            "dietary_tags": ["vegetarian", "gluten-free"],
            "ingredients": [
                "28 oz canned crushed tomatoes",
                "1 cup vegetable broth",
                "1/2 cup heavy cream",
                "1/4 cup fresh basil leaves",
                "1 medium yellow onion, diced",
                "3 cloves garlic, minced",
            ],
            "instructions": [
                "Sauté diced onion and garlic in olive oil until soft.",
                "Add crushed tomatoes and vegetable broth; simmer for 15 minutes.",
                "Blend soup until smooth using an immersion blender.",
                "Stir in heavy cream and fresh basil, then season to taste.",
            ],
        },
        {
            "id": "vegan-quinoa-buddha-bowl",
            "title": "Vegan Quinoa Buddha Bowl",
            "cuisine": "Mediterranean",
            "prep_time_minutes": 15,
            "cook_time_minutes": 20,
            "servings": 2,
            "dietary_tags": ["vegan", "vegetarian", "gluten-free", "healthy"],
            "ingredients": [
                "1 cup cooked quinoa",
                "1 cup chickpeas, drained and rinsed",
                "1 ripe avocado, sliced",
                "1 cup roasted sweet potatoes",
                "2 tbsp tahini dressing",
                "1 cup fresh arugula",
            ],
            "instructions": [
                "Divide quinoa, chickpeas, roasted sweet potatoes, and arugula between 2 bowls.",
                "Top with sliced avocado.",
                "Drizzle tahini dressing over top before serving.",
            ],
        },
    ]

    for recipe in initial_recipes:
        doc_ref = recipes_ref.document(recipe["id"])
        doc_ref.set(recipe)
        print(f"Seeded recipe: {recipe['title']}")

    # Seed pantry collection
    pantry_ref = db.collection("pantry")
    initial_pantry = [
        {"id": "olive-oil", "item_name": "Extra Virgin Olive Oil", "category": "Oils & Vinegars", "quantity": "1 bottle"},
        {"id": "garlic", "item_name": "Fresh Garlic", "category": "Produce", "quantity": "1 bulb"},
        {"id": "quinoa", "item_name": "Organic Quinoa", "category": "Grains", "quantity": "2 lbs"},
        {"id": "heavy-cream", "item_name": "Heavy Cream", "category": "Dairy", "quantity": "1 pint"},
        {"id": "chicken-breast", "item_name": "Boneless Chicken Breast", "category": "Meat", "quantity": "2 lbs"},
    ]

    for pantry_item in initial_pantry:
        doc_ref = pantry_ref.document(pantry_item["id"])
        doc_ref.set(pantry_item)
        print(f"Seeded pantry item: {pantry_item['item_name']}")

    print("Firestore seeding complete! ✅")


if __name__ == "__main__":
    seed_database()
