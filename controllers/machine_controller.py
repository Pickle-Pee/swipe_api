from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Embedding, Flatten, Dense, Concatenate
from tensorflow.keras.optimizers import Adam
import numpy as np

# Simulated user data
# age, gender (0 for male, 1 for female), city (encoded), interests (encoded)
user_data = np.array([[25, 0, 1, 3],
                      [30, 1, 2, 4],
                      [22, 0, 1, 1]])

# Simulated user-item interaction data (user_id, item_id, interaction)
interaction_data = np.array([[0, 1, 1],
                             [1, 2, 1],
                             [2, 3, 1]])

# User attributes input
user_input = Input(shape=(4,), name='user_input')

# Item input (for collaborative filtering)
item_input = Input(shape=(1,), name='item_input')

# User layers
x1 = Dense(10, activation='relu')(user_input)

# Item layers (for collaborative filtering)
x2 = Embedding(input_dim=1000, output_dim=5)(item_input)  # Assuming 1000 items
x2 = Flatten()(x2)

# Concatenate user and item layers
x = Concatenate()([x1, x2])

# Final layers
x = Dense(10, activation='relu')(x)
output = Dense(1, activation='sigmoid')(x)  # Output between 0 and 1 to represent interaction likelihood

# Create model
model = Model(inputs=[user_input, item_input], outputs=[output])

# Compile model
model.compile(optimizer=Adam(), loss='binary_crossentropy', metrics=['accuracy'])

# Fit model (using random data for demonstration)
model.fit([user_data, interaction_data[:, 1]], interaction_data[:, 2], epochs=10)