# Contributing to TTS Shorts Generator

Thank you for considering contributing to TTS Shorts Generator! We welcome contributions from everyone.

## 🎯 Ways to Contribute

### 🐛 Bug Reports
- Use the GitHub issue tracker
- Include detailed reproduction steps
- Mention your operating system and Python version
- Include error messages and logs

### 💡 Feature Requests
- Check existing issues first
- Describe the use case and benefits
- Consider implementation complexity
- Be open to discussion and alternatives

### 🔧 Code Contributions
- Fork the repository
- Create a feature branch (`git checkout -b feature/amazing-feature`)
- Make your changes
- Test thoroughly
- Submit a pull request

## 🛠️ Development Setup

### Environment Setup
```bash
git clone https://github.com/yourusername/tts-shorts-generator.git
cd tts-shorts-generator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -e .[dev]
```

### Code Quality
We use several tools to maintain code quality:

```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8 .

# Type checking
mypy app/
```

### Testing
```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app/
```

## 📋 Coding Standards

### Python Style
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Use [Black](https://github.com/psf/black) for formatting
- Maximum line length: 100 characters
- Use type hints where possible

### Commit Messages
Follow the [Conventional Commits](https://www.conventionalcommits.org/) format:
```
type(scope): description

feat(tts): add new voice options
fix(video): resolve split-screen alignment
docs(readme): update installation instructions
```

Types:
- `feat`: New features
- `fix`: Bug fixes
- `docs`: Documentation changes
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

## 🏗️ Project Structure

```
├── app/                    # Core application logic
│   ├── tts/               # Text-to-speech modules
│   ├── video.py           # Video processing
│   ├── captions.py        # Caption generation
│   └── youtube_uploader.py # YouTube integration
├── scripts/               # Utility scripts
├── examples/              # Sample files and demos
├── assets/                # Static assets
├── static/                # Web interface assets
├── templates/             # HTML templates
├── tests/                 # Test files (to be added)
└── docs/                  # Documentation (to be added)
```

## 🎨 UI/UX Guidelines

### Web Interface
- Maintain responsive design
- Use consistent color scheme
- Ensure accessibility (WCAG 2.1 AA)
- Test on multiple browsers
- Keep user experience simple and intuitive

### Desktop App
- Native window behavior
- Proper error handling and user feedback
- Progress indicators for long operations
- Graceful degradation when services are unavailable

## 🧪 Testing Guidelines

### What to Test
- Core video generation functionality
- TTS integration and error handling
- YouTube upload queue management
- File handling and cleanup
- User interface interactions

### Test Structure
```python
def test_function_name():
    # Arrange
    setup_test_data()
    
    # Act
    result = function_under_test()
    
    # Assert
    assert result == expected_value
```

## 📚 Documentation

### Code Documentation
- Use descriptive function and variable names
- Add docstrings for public functions
- Include type hints
- Comment complex logic

### User Documentation
- Update README.md for new features
- Add examples for new functionality
- Update troubleshooting guides
- Keep installation instructions current

## 🔄 Pull Request Process

1. **Before Starting**
   - Check existing issues and PRs
   - Discuss major changes in an issue first
   - Ensure your fork is up to date

2. **Development**
   - Create a feature branch
   - Make focused, atomic commits
   - Write tests for new functionality
   - Update documentation as needed

3. **Before Submitting**
   - Run all tests and linting
   - Test the UI thoroughly
   - Update CHANGELOG.md if applicable
   - Rebase on latest main branch

4. **Submitting**
   - Use a clear, descriptive title
   - Reference related issues
   - Provide detailed description
   - Include screenshots for UI changes

5. **After Submitting**
   - Respond to feedback promptly
   - Make requested changes
   - Keep the PR updated with main branch

## 🚀 Release Process

1. Version bumping follows [Semantic Versioning](https://semver.org/)
2. Update CHANGELOG.md with new features and fixes
3. Tag releases with `git tag v1.0.0`
4. Create GitHub releases with release notes

## ❓ Questions?

- Check existing [GitHub Issues](https://github.com/yourusername/tts-shorts-generator/issues)
- Start a [GitHub Discussion](https://github.com/yourusername/tts-shorts-generator/discussions)
- Review the [README.md](README.md) for basic usage

## 📜 Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct:

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect different viewpoints and experiences
- Show empathy towards other community members

---

**Happy Contributing! 🎉**

Your contributions help make TTS Shorts Generator better for everyone!
