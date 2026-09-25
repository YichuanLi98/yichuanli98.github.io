(function () {
  const lightbox = document.querySelector("#gallery-lightbox");
  const lightboxImage = lightbox.querySelector(".lightbox-image");
  const lightboxCount = lightbox.querySelector(".lightbox-count");
  const closeButton = lightbox.querySelector(".lightbox-close");
  const galleryItems = Array.from(document.querySelectorAll(".gallery-item"));
  let activeItem = null;

  function openLightbox(item, index) {
    activeItem = item;
    lightboxImage.src = item.dataset.full;
    lightboxImage.alt = item.dataset.alt;
    lightboxCount.textContent = `${String(index + 1).padStart(2, "0")} / ${String(galleryItems.length).padStart(2, "0")}`;
    lightbox.showModal();
    document.body.classList.add("lightbox-open");
  }

  function closeLightbox() {
    lightbox.close();
  }

  galleryItems.forEach((item, index) => {
    item.addEventListener("click", () => openLightbox(item, index));
  });

  closeButton.addEventListener("click", closeLightbox);

  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) {
      closeLightbox();
    }
  });

  lightbox.addEventListener("close", () => {
    document.body.classList.remove("lightbox-open");
    lightboxImage.src = "";
    if (activeItem) {
      activeItem.focus();
    }
  });
})();
