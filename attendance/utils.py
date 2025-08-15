import cv2
import numpy as np
import torch
import logging
import pickle
from facenet_pytorch import MTCNN, InceptionResnetV1
from django.conf import settings

logger = logging.getLogger(__name__)

class FaceRecognizer:
    def __init__(self):
        # Initialize with stricter face detection parameters
        self.mtcnn = MTCNN(
            keep_all=True,
            device='cpu',
            post_process=False,
            min_face_size=60,  # Larger minimum face size for better quality
            thresholds=[0.7, 0.8, 0.8]  # Higher detection thresholds for more accuracy
        )
        self.resnet = InceptionResnetV1(
            pretrained='vggface2',
            device='cpu'
        ).eval()
        self.known_faces = {}
        self.load_known_faces()

    def load_known_faces(self):
        """Load registered face encodings with error handling"""
        try:
            from .models import FaceProfile
            self.known_faces = {}
            for profile in FaceProfile.objects.all():
                if profile.face_encoding:
                    self.known_faces[profile.user_id] = {
                        'encoding': pickle.loads(profile.face_encoding),
                        'user_id': profile.user_id
                    }
        except Exception as e:
            logger.error(f"Error loading known faces: {str(e)}")
            self.known_faces = {}

    def detect_faces(self, frame):
        """More robust face detection with error handling"""
        try:
            if frame is None or frame.size == 0:
                logger.error("Empty frame received for detection")
                return []
                
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            boxes, probs = self.mtcnn.detect(rgb_frame)
            
            # Filter by confidence threshold for better accuracy
            if boxes is not None and probs is not None:
                valid_boxes = [box for box, prob in zip(boxes, probs) if prob > 0.95]
                return valid_boxes if valid_boxes else []
            return []
        except Exception as e:
            logger.error(f"Face detection failed: {str(e)}")
            return []

    def get_face_embedding(self, frame, box):
        """More resilient embedding extraction with normalization"""
        try:
            if frame is None or frame.size == 0:
                return None
                
            x1, y1, x2, y2 = map(int, box)
            
            # Add padding to the face region
            padding = int((x2 - x1) * 0.1)  # Reduced padding for more accurate face
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(frame.shape[1], x2 + padding)
            y2 = min(frame.shape[0], y2 + padding)
            
            face = frame[y1:y2, x1:x2]
            if face.size == 0:
                return None
                
            # Preprocessing for better quality
            face = cv2.resize(face, (160, 160))
            face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
            
            # Convert to tensor
            face_tensor = torch.tensor(face).float()
            face_tensor = face_tensor.permute(2, 0, 1).unsqueeze(0) / 255.0  # Normalize
            
            # Get embedding and normalize it
            embedding = self.resnet(face_tensor).detach().numpy().flatten()
            embedding = embedding / np.linalg.norm(embedding)  # L2 normalization
            
            return embedding
        except Exception as e:
            logger.error(f"Embedding extraction failed: {str(e)}")
            return None

    def process_frame(self, frame):
        """Enhanced face validation with better error handling"""
        try:
            if frame is None or frame.size == 0:
                return {'is_valid': False, 'error': 'Empty image received'}
                
            boxes = self.detect_faces(frame)
            if len(boxes) == 0:
                return {'is_valid': False, 'error': 'No faces detected. Please ensure your face is visible and well-lit'}
            
            if len(boxes) > 1:
                return {'is_valid': False, 'error': 'Multiple faces detected. Please ensure only your face is in the frame'}
            
            # Get the largest face
            main_box = max(boxes, key=lambda box: (box[2]-box[0])*(box[3]-box[1]))
            
            # Size check
            face_height = main_box[3] - main_box[1]
            face_width = main_box[2] - main_box[0]
            
            if face_height < frame.shape[0] * 0.2:  # Face should be at least 20% of frame height
                return {'is_valid': False, 'error': 'Please move closer to the camera'}
            
            if face_width < frame.shape[1] * 0.2:  # Face should be at least 20% of frame width
                return {'is_valid': False, 'error': 'Please center your face in the frame'}
            
            return {
                'is_valid': True,
                'face_location': main_box.tolist(),
                'face_count': len(boxes)
            }
        except Exception as e:
            logger.error(f"Frame processing failed: {str(e)}")
            return {'is_valid': False, 'error': 'Error processing image'}
            
    def identify_user(self, frame, face_location=None):
        """Identify a user from a frame using face recognition with stricter matching"""
        try:
            if not self.known_faces:
                return None
                
            if face_location is None:
                result = self.process_frame(frame)
                if not result.get('is_valid', False):
                    return None
                face_location = result['face_location']
                
            embedding = self.get_face_embedding(frame, face_location)
            if embedding is None:
                return None
                
            # Compare with all known faces
            best_match = None
            best_similarity = -1
            
            for user_id, data in self.known_faces.items():
                stored_encoding = data['encoding']
                # Use cosine similarity for better matching
                similarity = np.dot(embedding, stored_encoding)
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = user_id
            
            # Use a higher threshold for stricter matching
            threshold = getattr(settings, 'FACE_RECOGNITION_TOLERANCE', 0.8)
            if best_similarity > threshold:
                return best_match
                
            return None
        except Exception as e:
            logger.error(f"User identification error: {str(e)}")
            return None

    def verify_user_face(self, user_id, frame, face_location=None):
        """Verify if the face in the frame matches the given user with stricter matching"""
        try:
            if user_id not in self.known_faces:
                return False
                
            if face_location is None:
                result = self.process_frame(frame)
                if not result.get('is_valid', False):
                    return False
                face_location = result['face_location']
                
            embedding = self.get_face_embedding(frame, face_location)
            if embedding is None:
                return False
                
            # Compare with stored encoding
            stored_encoding = self.known_faces[user_id]['encoding']
            similarity = np.dot(embedding, stored_encoding)
            
            # Use a higher threshold for stricter matching
            threshold = getattr(settings, 'FACE_RECOGNITION_TOLERANCE', 0.8)
            return similarity > threshold
        except Exception as e:
            logger.error(f"Face verification error: {str(e)}")
            return False

face_recognizer = FaceRecognizer()