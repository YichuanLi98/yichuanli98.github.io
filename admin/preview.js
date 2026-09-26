(function () {
  const h = React.createElement;

  function value(entry, path, fallback) {
    const result = entry.getIn(["data"].concat(path.split(".")));
    return result === undefined || result === null ? (fallback || "") : result;
  }

  function assetUrl(getAsset, image) {
    if (!image) {
      return "";
    }
    const asset = getAsset(image);
    return asset ? asset.toString() : "";
  }

  function SiteSettingsPreview(props) {
    const entry = props.entry;
    const comingSoon = value(entry, "sections.painting.coming_soon", true);

    return h(
      "div",
      { className: "cms-site-preview" },
      h(
        "section",
        { className: "hero cms-preview-hero" },
        h("div", { className: "hero-shade" }),
        h(
          "div",
          { className: "hero-copy" },
          h("p", { className: "eyebrow" }, value(entry, "hero.eyebrow")),
          h(
            "h1",
            null,
            h("span", null, value(entry, "hero.heading_first")),
            h("span", null, value(entry, "hero.heading_second")),
          ),
          h("p", { className: "hero-discipline" }, value(entry, "hero.discipline")),
        ),
      ),
      h(
        "section",
        { className: "photography cms-copy-preview" },
        h(
          "div",
          { className: "section-heading" },
          h("p", { className: "eyebrow" }, value(entry, "sections.photography.eyebrow")),
          h("h2", null, value(entry, "sections.photography.heading")),
          h("p", { className: "section-note" }, value(entry, "sections.photography.note")),
        ),
      ),
      comingSoon
        ? h(
            "section",
            { className: "painting painting-holding" },
            h("div", { className: "painting-orbit", "aria-hidden": "true" },
              h("span", null, value(entry, "sections.painting.orbit_text")),
            ),
            h(
              "div",
              { className: "painting-copy" },
              h("p", { className: "eyebrow" }, value(entry, "sections.painting.eyebrow")),
              h("h2", null, value(entry, "sections.painting.heading")),
              h("p", null, value(entry, "sections.painting.note")),
            ),
          )
        : h(
            "section",
            { className: "photography cms-copy-preview" },
            h("p", { className: "eyebrow" }, value(entry, "sections.painting.eyebrow")),
            h("h2", null, value(entry, "sections.painting.heading")),
          ),
    );
  }

  function WorkPreview(props) {
    const entry = props.entry;
    const image = value(entry, "image");
    const title = value(entry, "title", "Untitled");
    const alt = value(entry, "alt", title);
    const category = value(entry, "category", "artwork");

    return h(
      "section",
      { className: "photography cms-work-preview" },
      h(
        "div",
        { className: "section-heading" },
        h("p", { className: "eyebrow" }, category),
        h("h2", null, title),
        h("p", { className: "section-note" }, value(entry, "description")),
      ),
      h(
        "div",
        { className: "gallery", "data-category": category },
        h(
          "button",
          { className: "gallery-item", type: "button" },
          h("span", { className: "work-number", "aria-hidden": "true" }, "01"),
          image
            ? h("img", {
                className: "gallery-image",
                src: assetUrl(props.getAsset, image),
                alt: alt,
              })
            : h("span", { className: "cms-missing-image" }, "请选择图片"),
        ),
      ),
    );
  }

  function PhotographyPreview(props) {
    return WorkPreview(props);
  }

  function PaintingPreview(props) {
    return WorkPreview(props);
  }

  CMS.registerPreviewStyle("/admin/preview.css");
  CMS.registerPreviewTemplate("site_settings", SiteSettingsPreview);
  CMS.registerPreviewTemplate("photography", PhotographyPreview);
  CMS.registerPreviewTemplate("painting", PaintingPreview);
})();
