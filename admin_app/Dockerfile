# Use an official Python runtime as a parent image
FROM python:3.11

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY requirements.txt /app/
# Install any needed packages specified in requirements.txt
RUN pip install --trusted-host pypi.python.org -r /app/requirements.txt

COPY . /app

# Make port 80 available to the world outside this container
EXPOSE 1027

# Run your application
CMD ["python", "/app/admin_app/app.py"]
