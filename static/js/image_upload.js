// Shared by admin.html and admin_projects.html - uploads a single image file
// and returns the server-relative path to store on the course/project.
async function uploadImageFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/admin/upload-image", { method: "POST", body: formData });
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.detail || data.error || "Upload failed");
  return data.path;
}

// Wires a <input type="file">, a text <input> holding the path, and an
// <img> preview together: picking a file uploads it, fills the text input,
// and updates the preview. Also keeps the preview in sync if the path is
// edited by hand.
function wireImageUploadField(fileInputId, pathInputId, previewId) {
  const fileInput = document.getElementById(fileInputId);
  const pathInput = document.getElementById(pathInputId);
  const preview = document.getElementById(previewId);

  function updatePreview() {
    if (preview) {
      preview.src = pathInput.value || "";
      preview.style.display = pathInput.value ? "block" : "none";
    }
  }

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    try {
      const path = await uploadImageFile(file);
      pathInput.value = path;
      updatePreview();
    } catch (err) {
      alert(`Image upload failed: ${err.message}`);
    } finally {
      fileInput.value = "";
    }
  });

  pathInput.addEventListener("input", updatePreview);
  updatePreview();
}
