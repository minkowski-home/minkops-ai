import os.path
import sys
import typing
from typing import Union, Optional, Any, List, Tuple
import cv2
import face_recognition
import numpy as np
# from src.gui.main_app import CameraManager

def convert_to_encoding(*, file: Union[str, None] = None, frame=None, return_locations_only: bool = False):
    """
    Convert a given image file or video feed into face encoding.

    Parameters:
    - file (Union[str, None]): The path to the image file or None for webcam feed.

    Returns:
    - Union[Tuple[str, Any], Tuple[None, Any]]: A tuple containing the person's name and encoding
      if an image file is provided, otherwise None and the encoding from the webcam feed.
    """

    if file:
        person_name = os.path.basename(file).split('.')[0]

        image = cv2.imread(file)
        face_locations = face_recognition.face_locations(image)
        if return_locations_only:
            return image, face_locations
        encodings = face_recognition.face_encodings(image, face_locations)

        # Returning only the first encoding, multiple encoding support pending.
        return person_name, encodings[0]
    elif frame is not None:
        face_locations = face_recognition.face_locations(frame)
        if face_locations:  # Check if any face is detected
            if return_locations_only:
                return frame, face_locations
            encodings = face_recognition.face_encodings(frame, face_locations)
            return None, encodings[0]  # Return the first encoding
        else:
            if return_locations_only:
                return frame, face_locations
            return None, None


def store_into_database(*, file: Optional[str] = None, frame=None, cursor: Any) -> None:
    """
    Store a person's face encoding into the database.

    Parameters:
        - file (Optional[str]): The path to the image file. Default is None, in which case it will capture
          frames from live video feed.
        - cursor (Any): The database cursor for executing SQL commands.

    Returns:
        - None: The function performs database insertion and returns nothing.
    """

    person_name, encoding = convert_to_encoding(file=file, frame=frame)
    query = 'INSERT INTO faces(person_name, face_encoding) VALUES (%s, %s)'

    encoding_bytes = encoding.tobytes()
    val = (person_name, encoding_bytes)

    cursor.execute(query, val)


def read_encoding_from_database(face_id: Union[int, List[int], str], cursor: Any) -> typing.Dict:
    """
    Fetch face encoding(s) from the database given the face ID(s).

    Parameters:
    - face_id (Union[int, List[int]]): A single face ID or a list of face IDs.
    - cursor (pymysql.cursors.Cursor): Database cursor for executing SQL queries.

    Returns:
    - List[np.ndarray]: A list of numpy arrays representing face encodings.

    Raises:
    - FileNotFoundError: If any of the face IDs do not have an associated encoding.
    """

    # Prepares variables for batch operation if face_id is a list, and for single operation if face_id is a
    # single index
    placeholder = ', '.join(['%s'] * len(face_id)) if not isinstance(face_id, int) else '%s'
    face_id = (face_id,) if isinstance(face_id, int) else face_id

    if face_id == 'all':
        query = 'SELECT face_id, face_encoding, person_name FROM faces'
        cursor.execute(query)
    else:
        query = f'SELECT face_id, face_encoding, person_name FROM faces WHERE face_id IN ({placeholder})'
        cursor.execute(query, face_id)
    rows = cursor.fetchall()

    # Check if any row has None value
    if any(None in row for row in rows):
        idx = next((i for i, row in enumerate(rows) if None in row), None)
        raise FileNotFoundError(f"Encoding with ID {idx} not found in the database.")

    encoding_dict = {(face_id, person_name): np.frombuffer(encoding) for face_id, encoding, person_name in rows}

    return encoding_dict


def match_face(*, file=None, frame=None, cursor):
    encoding_dict = read_encoding_from_database('all', cursor)
    current_person_name, current_encoding = convert_to_encoding(file=file, frame=frame)
    if current_encoding is None:
        return None, None, None
    all_encodings = list(encoding_dict.values())
    matches = face_recognition.compare_faces(all_encodings, current_encoding, tolerance=0.6)  # list of Booleans
    for idx, match in enumerate(matches):
        if match:
            matched_key = list(encoding_dict.keys())[idx]
            face_id, person_name = matched_key
            return face_id, person_name, current_encoding
        else:
            return None, None, current_encoding


def draw_bounding_boxes(*, file=None, frame=None):
    # Assuming you have a face detection method implemented
    frame, face_locations = convert_to_encoding(file=file, frame=frame, return_locations_only=True)

    for (top, right, bottom, left) in face_locations:
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

    return frame


def crop_face_from_frame(frame):
    # Find all face locations in the frame
    face_locations = face_recognition.face_locations(frame)

    # Assuming the first face is the one we want to crop
    if face_locations:
        top, right, bottom, left = face_locations[0]
        face_image = frame[top:bottom, left:right]

        return face_image
    else:
        return None  # No faces found in the frame


# PENDING IMMEDIATELY
# Modify read_encodings_from_database() to process in batches
# Replace face-recognition with opencv's dnn
