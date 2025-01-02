from flask import Flask, request, jsonify
from flask_restx import Api, Resource, fields
import logging
import os
import cloudinary
import cloudinary.uploader
import pyodbc
import cv2
import numpy as np
import urllib.request

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Cloudinary Configuration
cloudinary.config(
    cloud_name="dti4ah9gr",
    api_key="455798993897116",
    api_secret="vshhZXiIhvzENBBblhbAXLXjxXs"
)

# Flask app and API initialization
app = Flask(__name__)
api = Api(app)

# API Models for Swagger Docs
image_upload_model = api.model('ImageUpload', {
    'segment_id': fields.Integer(required=True, description='Segment ID of the car'),
    'model_type': fields.String(required=True, description='Model type of the car'),
    'image_paths': fields.Raw(required=True, description='A dictionary of image paths with column names as keys')
})

# Database Configuration
db_config = {
    'server': 'mohitsikhan.database.windows.net',
    'database': 'car_rent',
    'user': 'mohitsikhan',
    'password': 'Mohit@210',
}

def retrieve_image_url_from_db(segment_id, model_type, column, db_config):
    """Retrieve the image URL for the specified segment_id and model_type from the database."""
    try:
        conn_str = (
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server={db_config['server']};"
            f"Database={db_config['database']};"
            f"UID={db_config['user']};"
            f"PWD={db_config['password']};"
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        query = f"""
            SELECT car_id, segment_id, segment_name, model_type, {column}
            FROM cars
            WHERE model_type = ? AND segment_id = ?
        """
        
        cursor.execute(query, (model_type, segment_id))
        results = cursor.fetchall()

        if results:
            cars = []
            for row in results:
                cars.append({
                    'car_id': row[0],
                    'segment_id': row[1],
                    'segment_name': row[2],
                    'model_type': row[3],
                    'image_url': row[4]  # The image URL column
                })
            logging.info(f"Successfully retrieved image URLs for segment_id '{segment_id}' and model_type '{model_type}'.")
            return cars
        else:
            logging.warning(f"No cars found for model_type '{model_type}' and segment_id '{segment_id}'.")
            return []
    except pyodbc.Error as e:
        logging.error(f"Error retrieving image URLs for segment_id '{segment_id}' and model_type '{model_type}': {e}")
        return []
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def upload_image_to_cloudinary(image_path):
    """Upload image to Cloudinary and return the secure URL."""
    try:
        response = cloudinary.uploader.upload(image_path)
        return response['secure_url']
    except Exception as e:
        logging.error(f"Error uploading image to Cloudinary: {e}")
        return None

def detect_scratches_or_differences(new_image_path, existing_image_url):
    """Advanced method to detect scratches or differences in the images."""
    try:
        new_image = cv2.imread(new_image_path, cv2.IMREAD_GRAYSCALE)
        if new_image is None:
            logging.error("Failed to load the new image.")
            return False

        resp = urllib.request.urlopen(existing_image_url)
        existing_image_data = np.asarray(bytearray(resp.read()), dtype="uint8")
        existing_image = cv2.imdecode(existing_image_data, cv2.IMREAD_GRAYSCALE)
        if existing_image is None:
            logging.error("Failed to load the existing image from Cloudinary.")
            return True

        new_image_resized = cv2.resize(new_image, (500, 500))
        existing_image_resized = cv2.resize(existing_image, (500, 500))

        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        new_image_enhanced = clahe.apply(new_image_resized)
        existing_image_enhanced = clahe.apply(existing_image_resized)

        diff_image = cv2.absdiff(new_image_enhanced, existing_image_enhanced)
        cv2.imwrite("debug_diff_image.jpg", diff_image)

        blurred_diff = cv2.GaussianBlur(diff_image, (7, 7), 0)
        cv2.imwrite("debug_blurred_diff.jpg", blurred_diff)

        edges = cv2.Canny(blurred_diff, 50, 200)
        cv2.imwrite("debug_edges.jpg", edges)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morphed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        cv2.imwrite("debug_morphed_edges.jpg", morphed_edges)

        contours, _ = cv2.findContours(morphed_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        scratch_detected = False
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 50:
                scratch_detected = True
                break

        if scratch_detected:
            logging.info("Scratches or differences detected between the images.")
        else:
            logging.info("No significant scratches or differences detected.")

        return scratch_detected

    except Exception as e:
        logging.error(f"Error detecting scratches or differences in images: {e}")
        return False

def update_images_for_segment(segment_id, model_type, image_paths, db_config):
    """Update Cloudinary image URLs for all cars matching the model_type and segment_id in the database."""
    result = []  # Collect results for each image

    for column, new_image_path in image_paths.items():
        logging.info(f"Processing image for column '{column}' (Segment: {segment_id}, Model: {model_type}).")

        cars = retrieve_image_url_from_db(segment_id, model_type, column, db_config)

        if not cars:
            logging.warning(f"No cars found for column '{column}' with model_type '{model_type}' and segment_id '{segment_id}'.")
            continue

        for car in cars:
            existing_image_url = car['image_url']

            if not os.path.exists(new_image_path):
                logging.error(f"New image file not found: {new_image_path}")
                result.append({'column': column, 'status': 'Error: File not found'})
                continue

            if existing_image_url:
                issues_detected = detect_scratches_or_differences(new_image_path, existing_image_url)

                if issues_detected:
                    logging.info(f"Scratches or differences detected for column '{column}', segment_id '{segment_id}', model_type '{model_type}'. Uploading new image.")
                    new_image_url = upload_image_to_cloudinary(new_image_path)

                    if new_image_url:
                        try:
                            conn_str = (
                                f"Driver={{ODBC Driver 18 for SQL Server}};"
                                f"Server={db_config['server']};"
                                f"Database={db_config['database']};"
                                f"UID={db_config['user']};"
                                f"PWD={db_config['password']};"
                            )
                            conn = pyodbc.connect(conn_str)
                            cursor = conn.cursor()

                            cursor.execute(f"""
                                UPDATE cars
                                SET {column} = ?
                                WHERE segment_id = ? AND model_type = ?
                            """, (new_image_url, segment_id, model_type))
                            conn.commit()

                            if cursor.rowcount > 0:
                                logging.info(f"Successfully updated image URL for column '{column}', segment_id '{segment_id}', model_type '{model_type}'.")
                                result.append({'column': column, 'status': 'Scratches detected, image updated', 'new_image_url': new_image_url})
                            else:
                                logging.warning(f"No rows updated for column '{column}', segment_id '{segment_id}', model_type '{model_type}'.")
                                result.append({'column': column, 'status': 'No update made'})
                        except pyodbc.Error as e:
                            logging.error(f"Database error while updating column '{column}': {e}")
                            result.append({'column': column, 'status': f'Error: {str(e)}'})
                        finally:
                            if 'cursor' in locals():
                                cursor.close()
                            if 'conn' in locals():
                                conn.close()
                else:
                    logging.info(f"No scratches or differences detected for column '{column}', segment_id '{segment_id}', model '{model_type}'. Keeping existing image.")
                    result.append({'column': column, 'status': 'No scratches detected, image retained'})
            else:
                logging.warning(f"No existing image URL found for column '{column}', segment_id '{segment_id}', model_type '{model_type}'.")
                result.append({'column': column, 'status': 'No existing image URL'})

    return result

# Define Flask resource to expose the function
class ImageUploadResource(Resource):
    @api.expect(image_upload_model)
    def post(self):
        data = request.get_json()
        segment_id = data['segment_id']
        model_type = data['model_type']
        image_paths = data['image_paths']

        result = update_images_for_segment(segment_id, model_type, image_paths, db_config)
        return jsonify(result)

# Register the resource with Flask-RESTx
api.add_resource(ImageUploadResource, '/upload-images')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
