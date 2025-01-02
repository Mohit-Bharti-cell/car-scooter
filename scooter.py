from flask import Flask, request, jsonify
import pyodbc
import cloudinary
import cloudinary.uploader

app = Flask(__name__)


cloudinary.config(
    cloud_name="dti4ah9gr",
    api_key="455798993897116",
    api_secret="vshhZXiIhvzENBBblhbAXLXjxXs"
)


db_config = {
    'server': 'mohitsikhan.database.windows.net',
    'database': 'car_rent',
    'user': 'mohitsikhan',
    'password': 'Mohit@210',
}

def get_db_connection():
    """Establish a connection to the Azure SQL Database."""
    return pyodbc.connect(
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={db_config['server']};"
        f"Database={db_config['database']};"
        f"UID={db_config['user']};"
        f"PWD={db_config['password']};"
    )

def create_table(cursor):
    """Create the scooter_ev table if it does not already exist."""
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='scooter_ev' AND xtype='U')
        BEGIN
            CREATE TABLE scooter_ev (
                scooter_id INT PRIMARY KEY IDENTITY(1,1),
                scooter_name NVARCHAR(255) NOT NULL,
                segment_id INT NOT NULL,
                segment_name NVARCHAR(255) NOT NULL,
                model_type NVARCHAR(255),
                year INT,
                motor_type NVARCHAR(255),
                battery_type NVARCHAR(255),
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

@app.route("/upload-scooter", methods=["POST"])
def upload_scooter():
    """Endpoint to upload scooter details and images."""
    data = request.json
    image_paths = data.get("image_paths", {})
    scooter_name = data.get("scooter_name")
    segment_id = data.get("segment_id")
    segment_name = data.get("segment_name")
    model_type = data.get("model_type")
    year = data.get("year")
    motor_type = data.get("motor_type")
    battery_type = data.get("battery_type")
    price = data.get("price")

    if not all([scooter_name, segment_id, segment_name, model_type, year, motor_type, battery_type, price, image_paths]):
        return jsonify({"error": "Missing required fields"}), 400

    image_urls = {}
    for column, image_path in image_paths.items():
        try:
            response = cloudinary.uploader.upload(image_path)
            image_urls[column] = response.get("secure_url")
        except Exception as e:
            return jsonify({"error": f"Failed to upload {column}: {e}"}), 500

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        create_table(cursor)

        # Insert scooter details
        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM scooter_ev WHERE model_type = ? AND segment_id = ?
            )
            INSERT INTO scooter_ev (scooter_name, segment_id, segment_name, model_type, year, motor_type, battery_type, price,
                                   image_data, front_view, back_view, left_side_view, right_side_view)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model_type, segment_id,
            scooter_name, segment_id, segment_name, model_type, year, motor_type, battery_type, price,
            image_urls.get("image_data"), image_urls.get("front_view"),
            image_urls.get("back_view"), image_urls.get("left_side_view"),
            image_urls.get("right_side_view")
        ))
        cursor.commit()
        return jsonify({"message": f"Scooter '{scooter_name}' uploaded successfully."}), 201
    except pyodbc.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
