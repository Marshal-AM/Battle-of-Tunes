import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
import librosa
import soundfile as sf
import warnings
warnings.filterwarnings('ignore')

class PopMusicEvaluator:
    def __init__(self):
        self.scaler = MinMaxScaler()
        self.model = RandomForestRegressor(
            n_estimators=100,
            random_state=42
        )
        self.feature_columns = [
            'acousticness', 'danceability', 'energy',
            'instrumentalness', 'key', 'liveness',
            'loudness'
        ]

    def prepare_dataset(self, dataset_path):
        """Load dataset from CSV and prepare it"""
        # Read CSV file
        df = pd.read_csv(dataset_path)

        # Convert numeric columns
        numeric_columns = [
            'song_popularity', 'song_duration_ms', 'acousticness',
            'danceability', 'energy', 'instrumentalness', 'key',
            'liveness', 'loudness'
        ]

        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    def train_model(self, dataset_path):
        """Train the model using the provided dataset"""
        # Prepare dataset
        df = self.prepare_dataset("/content/song_data.csv")

        # Create target variable (song quality score)
        quality_score = df['song_popularity'].values.reshape(-1, 1)
        quality_score_normalized = self.scaler.fit_transform(quality_score)

        # Prepare features
        X = df[self.feature_columns]

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, quality_score_normalized,
            test_size=0.2,
            random_state=42
        )

        # Train model
        self.model.fit(X_train, y_train.ravel())

        # Store feature ranges for validation
        self.feature_ranges = {
            column: (df[column].min(), df[column].max())
            for column in self.feature_columns
        }

        return self.model.score(X_test, y_test)

    def extract_features(self, audio_file):
        """Extract audio features from a 5-second track"""
        # Load audio file
        y, sr = librosa.load(audio_file, duration=5)

        # Extract features
        features = {}

        # Spectral features
        features['acousticness'] = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
        features['energy'] = np.mean(librosa.feature.rms(y=y))

        # Rhythm features
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        features['danceability'] = tempo / 200.0  # Normalize tempo

        # Harmonic features
        harmonic, percussive = librosa.effects.hpss(y)
        features['instrumentalness'] = np.mean(harmonic) / (np.mean(harmonic) + np.mean(percussive))

        # Key detection
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        features['key'] = np.argmax(np.mean(chroma, axis=1))

        # Liveness detection (based on signal statistics)
        features['liveness'] = np.mean(librosa.feature.zero_crossing_rate(y))

        # Loudness
        features['loudness'] = librosa.amplitude_to_db(np.mean(np.abs(y)))

        return features

    def evaluate_track(self, audio_file):
        """Evaluate a single audio track"""
        # Extract features
        features = self.extract_features(audio_file)

        # Prepare features for prediction
        X = pd.DataFrame([features])[self.feature_columns]

        # Make prediction
        quality_score = self.model.predict(X)[0]

        # Convert to percentage
        quality_score = self.scaler.inverse_transform([[quality_score]])[0][0]

        return {
            'quality_score': quality_score,
            'features': features
        }

    def compare_tracks(self, track1_file, track2_file):
        """Compare two tracks and determine which is better"""
        # Evaluate both tracks
        track1_eval = self.evaluate_track(track1_file)
        track2_eval = self.evaluate_track(track2_file)

        # Compare scores
        if track1_eval['quality_score'] > track2_eval['quality_score']:
            better_track = 'Track 1'
            score_diff = track1_eval['quality_score'] - track2_eval['quality_score']
        else:
            better_track = 'Track 2'
            score_diff = track2_eval['quality_score'] - track1_eval['quality_score']

        return {
            'better_track': better_track,
            'score_difference': score_diff,
            'track1_evaluation': track1_eval,
            'track2_evaluation': track2_eval
        }


from google.colab import files

def main_colab():
    # Initialize evaluator
    evaluator = PopMusicEvaluator()

    # Upload your dataset file (CSV)
    print("Upload your dataset CSV file:")
    uploaded = files.upload()
    dataset_path = list(uploaded.keys())[0]

    # Train the model
    print("\nTraining the model...")
    model_score = evaluator.train_model(dataset_path)
    print(f"Model R² Score: {model_score:.4f}")

    # Upload audio files to compare
    print("\nUpload the first audio file:")
    uploaded_track1 = files.upload()
    track1_file = list(uploaded_track1.keys())[0]

    print("\nUpload the second audio file:")
    uploaded_track2 = files.upload()
    track2_file = list(uploaded_track2.keys())[0]

    # Compare tracks
    print("\nComparing tracks...")
    result = evaluator.compare_tracks(track1_file, track2_file)

    # Print results
    print(f"\nBetter track: {result['better_track']}")
    print(f"Score difference: {result['score_difference']:.2f}")

    print("\nTrack 1 Evaluation:")
    print(f"Quality Score: {result['track1_evaluation']['quality_score']:.2f}")
    print("\nFeatures:")
    for feature, value in result['track1_evaluation']['features'].items():
        # Ensure scalar values for formatting
        if isinstance(value, np.ndarray):
            value = value.item() if value.size == 1 else value.tolist()  # Convert single-element array to scalar
        print(f"{feature}: {value:.4f}" if isinstance(value, (int, float)) else f"{feature}: {value}")

    print("\nTrack 2 Evaluation:")
    print(f"Quality Score: {result['track2_evaluation']['quality_score']:.2f}")
    print("\nFeatures:")
    for feature, value in result['track2_evaluation']['features'].items():
        # Ensure scalar values for formatting
        if isinstance(value, np.ndarray):
            value = value.item() if value.size == 1 else value.tolist()  # Convert single-element array to scalar
        print(f"{feature}: {value:.4f}" if isinstance(value, (int, float)) else f"{feature}: {value}")

# Run the main function
main_colab()