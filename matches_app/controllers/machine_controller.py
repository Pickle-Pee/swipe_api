from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Embedding, Flatten, Dense, Concatenate
from tensorflow.keras.optimizers import legacy
from sqlalchemy import create_engine
import pandas as pd
from dotenv import load_dotenv
import os


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Database connection
engine = create_engine(DATABASE_URL)


# Fetch data from database
def fetch_data():
    users_df = pd.read_sql('SELECT id, date_of_birth, gender, verify FROM users', engine)
    user_interests_df = pd.read_sql('SELECT * FROM user_interests', engine)
    likes_df = pd.read_sql('SELECT user_id, liked_user_id, mutual FROM likes', engine)
    dislikes_df = pd.read_sql('SELECT user_id, disliked_user_id FROM dislikes', engine)

    # Convert date_of_birth to age
    users_df['age'] = 2023 - pd.DatetimeIndex(users_df['date_of_birth']).year

    # One-hot encoding for gender
    users_df = pd.get_dummies(users_df, columns=['gender'])

    # Merge user_interests with users
    merged_df = pd.merge(users_df, user_interests_df, left_on='id', right_on='user_id', how='left')

    # Prepare the data arrays
    user_data = merged_df[['age', 'gender_male', 'gender_female', 'verify', 'interest_id']].fillna(0).\
        values.astype('float32')
    likes_df['interaction'] = likes_df['mutual'].apply(lambda x: 1 if x else 0)
    interaction_data = likes_df[['user_id', 'liked_user_id', 'interaction']].values.astype('float32')

    print(user_data.shape, interaction_data.shape)

    return user_data, interaction_data


# User attributes input
user_input = Input(shape=(5,), name='user_input')

# Item input (for collaborative filtering)
item_input = Input(shape=(1,), name='item_input')

# User layers
x1 = Dense(10, activation='relu')(user_input)

# Item layers (for collaborative filtering)
x2 = Embedding(input_dim=1000, output_dim=5)(item_input)
x2 = Flatten()(x2)

# Concatenate user and item layers
x = Concatenate()([x1, x2])

# Final layers
x = Dense(10, activation='relu')(x)
output = Dense(1, activation='sigmoid')(x)

# Create model
model = Model(inputs=[user_input, item_input], outputs=[output])

# Compile model using legacy Adam optimizer to avoid M1/M2 Mac warning
model.compile(optimizer=legacy.Adam(), loss='binary_crossentropy', metrics=['accuracy'])

# Fetch data
user_data, interaction_data = fetch_data()

# Fit model
model.fit([user_data, interaction_data[:, 1]], interaction_data[:, 2], epochs=1000)

dir_path = os.path.dirname(os.path.realpath(__file__))
model_path = os.path.join(dir_path, '../..', 'utils', 'model.keras')
model.save(model_path)
