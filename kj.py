from flask import Flask, request, jsonify
import pyodbc
import cloudinary
import cloudinary.uploader
import os

app = Flask(__name__)

cloudinary.config(
    cloud_name="dti4ah9gr",
    api_key="455798993897116",
    api_secret="vshhZXiIhvzENBBblhbAXLXjxXs"
)

# Database configuration
db_config = {
    'server': 'mohitsikhan.database.windows.net',
    'database': 'car_rent',
    'user': 'mohitsikhan',
    'password': 'Mohit@210',
}

# Function to upload image to Cloudinary
def upload_image_to_dam(image_path):
    """Upload image to Cloudinary and return the URL."""
    try:
        response = cloudinary.uploader.upload(image_path)
        return response.get("secure_url")
    except Exception as e:
        print(f"Error uploading image: {e}")
        return None

# Function to create the table (if it doesn't exist)
def create_table(cursor):
    """Create the cars table if it does not already exist."""
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='cars' AND xtype='U')
        BEGIN
            CREATE TABLE cars (
                car_id INT PRIMARY KEY IDENTITY(1,1),
                car_name NVARCHAR(255) NOT NULL,
                segment_id INT NOT NULL,
                segment_name NVARCHAR(255) NOT NULL,
                model_type NVARCHAR(255),
                year INT,
                engine_type NVARCHAR(255),
                fuel_type NVARCHAR(255),
                price DECIMAL(10, 2),
                image_data NVARCHAR(MAX),
                front_view NVARCHAR(MAX),
                back_view NVARCHAR(MAX),
                left_side_view NVARCHAR(MAX),
                right_side_view NVARCHAR(MAX)
            );
        END;
    """)
    cursor.commit()

def insert_car_details(car_name, segment_id, segment_name, model_type, year, engine_type, fuel_type, price, image_urls, cursor):
    # Check if a car with the same details already exists
    cursor.execute("""
        SELECT 1 
        FROM cars 
        WHERE car_name = ? AND segment_id = ? AND model_type = ? AND year = ?
          AND engine_type = ? AND fuel_type = ? AND price = ?
    """, (car_name, segment_id, model_type, year, engine_type, fuel_type, price))
    
    if cursor.fetchone():
        return "Car with the same details already exists."

    # Insert new car details
    cursor.execute("""
        INSERT INTO cars (car_name, segment_id, segment_name, model_type, year, engine_type, fuel_type, price,
                          image_data, front_view, back_view, left_side_view, right_side_view)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        car_name, segment_id, segment_name, model_type, year, engine_type, fuel_type, price,
        image_urls.get("image_data"), image_urls.get("front_view"),
        image_urls.get("back_view"), image_urls.get("left_side_view"),
        image_urls.get("right_side_view")
    ))
    cursor.commit()
    return "Car details inserted successfully."


# API route for uploading images and inserting car details
@app.route('/upload_car', methods=['POST'])
def upload_car():
    data = request.json

    # Ensure all necessary data is provided
    required_fields = ['car_name', 'segment_id', 'segment_name', 'model_type', 'year', 'engine_type', 'fuel_type', 'price', 'image_paths']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    car_name = data['car_name']
    segment_id = data['segment_id']
    segment_name = data['segment_name']
    model_type = data['model_type']
    year = data['year']
    engine_type = data['engine_type']
    fuel_type = data['fuel_type']
    price = data['price']
    image_paths = data['image_paths']  # Dictionary of image file paths

    image_urls = {}

    # Upload each image to Cloudinary
    for column, image_path in image_paths.items():
        image_url = upload_image_to_dam(image_path)
        if image_url:
            image_urls[column] = image_url
        else:
            return jsonify({"error": f"Failed to upload image for {column}"}), 500

    try:
        conn = pyodbc.connect(
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server={db_config['server']};"
            f"Database={db_config['database']};"
            f"UID={db_config['user']};"
            f"PWD={db_config['password']};"
        )
        cursor = conn.cursor()

        create_table(cursor)
        result = insert_car_details(car_name, segment_id, segment_name, model_type, year, engine_type, fuel_type, price, image_urls, cursor)
        
        if result == "Car with the same details already exists.":
            return jsonify({"message": result}), 200
        
        return jsonify({"message": result}), 201

    except pyodbc.Error as e:
        print(f"Database error: {e}")
        return jsonify({"error": "Database error occurred"}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


# Main entry point to run the Flask app
if __name__ == "__main__":
    app.run(debug=True)