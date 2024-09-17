python -m venv venv
echo "Activating virtual environment..."
source venv/bin/activate
echo "Installing dependencies..."
pip install -r requirements.txt > /dev/null 2>&1
pip install pytest-sugar > /dev/null 2>&1  
echo "Running Discord Bot tests..."
pytest -v --tb=short
echo "Deactivating virtual environment..."
deactivate
echo "Done."