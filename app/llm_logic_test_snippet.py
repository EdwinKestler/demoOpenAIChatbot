from app.llm_logic import llm_classify_image

if __name__ == "__main__":
    # Use a local image path to force data URL path
    path = "public/4623dd28d0a448ccbed34eb02fbed584.jpg"  # replace with an actual file saved locally
    print(llm_classify_image(path, max_retries=1, force_detail="low"))