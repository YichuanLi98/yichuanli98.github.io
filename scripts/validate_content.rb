#!/usr/bin/env ruby

require "date"
require "open3"
require "optparse"
require "yaml"

SITE_KEYS = %w[owner seo navigation hero sections footer contact].freeze
WORK_REQUIRED_KEYS = %w[title category image alt visible].freeze
WORK_CATEGORIES = %w[photography painting].freeze
SUPPORTED_IMAGE_EXTENSIONS = %w[.jpg .jpeg .png .webp].freeze
MAX_IMAGE_BYTES = 15 * 1024 * 1024

def load_yaml(path)
  YAML.safe_load(
    File.read(path),
    permitted_classes: [Date],
    aliases: true
  )
rescue StandardError => error
  raise ArgumentError, "#{path}: invalid YAML: #{error.message}"
end

def load_work(path)
  text = File.read(path)
  match = text.match(/\A---\s*\n(.*?)\n---\s*(?:\n|\z)/m)
  raise ArgumentError, "#{path}: missing YAML front matter" unless match

  data = YAML.safe_load(
    match[1],
    permitted_classes: [Date],
    aliases: true
  ) || {}
  data["_path"] = path
  data["_slug"] = File.basename(path, File.extname(path))
  data
rescue Psych::Exception => error
  raise ArgumentError, "#{path}: invalid front matter: #{error.message}"
end

def validate_site(data)
  errors = []
  unless data.is_a?(Hash)
    return ["site: expected a mapping"]
  end

  missing = SITE_KEYS - data.keys.map(&:to_s)
  errors << "site: missing sections: #{missing.join(', ')}" unless missing.empty?

  featured_work = data.dig("hero", "featured_work") if data["hero"].is_a?(Hash)
  unless featured_work.is_a?(String) && !featured_work.strip.empty?
    errors << "site: hero.featured_work must name a photography work"
  end

  WORK_CATEGORIES.each do |category|
    section = data.dig("sections", category) if data["sections"].is_a?(Hash)
    order = section["work_order"] if section.is_a?(Hash)
    unless order.is_a?(Array)
      errors << "site: sections.#{category}.work_order must be a list"
      next
    end

    invalid = order.reject { |slug| slug.is_a?(String) && !slug.strip.empty? }
    errors << "site: sections.#{category}.work_order must contain work slugs" unless invalid.empty?
    duplicates = order.group_by(&:itself).select { |_slug, entries| entries.length > 1 }.keys
    unless duplicates.empty?
      errors << "site: sections.#{category}.work_order contains duplicates: #{duplicates.join(', ')}"
    end
  end
  errors
end

def validate_works(works)
  errors = []
  works.each do |work|
    path = work.fetch("_path", "work")
    missing = WORK_REQUIRED_KEYS.reject { |key| work.key?(key) }
    errors << "#{path}: missing fields: #{missing.join(', ')}" unless missing.empty?

    %w[title image alt].each do |field|
      value = work[field]
      errors << "#{path}: #{field} must not be empty" unless value.is_a?(String) && !value.strip.empty?
    end

    unless WORK_CATEGORIES.include?(work["category"])
      errors << "#{path}: category must be photography or painting"
    end
    errors << "#{path}: visible must be true or false" unless [true, false].include?(work["visible"])
  end

  visible_photos = works.select { |work| work["category"] == "photography" && work["visible"] == true }
  errors << "works: at least one visible photograph is required" if visible_photos.empty?

  errors
end

def validate_editor_relationships(site, works)
  return [] unless site.is_a?(Hash)

  featured_slug = site.dig("hero", "featured_work") if site["hero"].is_a?(Hash)
  return [] unless featured_slug.is_a?(String) && !featured_slug.strip.empty?

  featured_work = works.find { |work| work["_slug"] == featured_slug }
  if featured_work.nil? || featured_work["category"] != "photography" || featured_work["visible"] != true
    ["site: hero.featured_work must name a visible photography work: #{featured_slug}"]
  else
    []
  end
end

def validate_work_images(works, repo_root:, sanitizer: File.join(__dir__, "sanitize_media.py"))
  errors = []
  references = Hash.new { |hash, key| hash[key] = [] }
  root = File.expand_path(repo_root)

  works.each do |work|
    source = work.fetch("_path", "work")
    image = work["image"]
    next unless image.is_a?(String) && !image.strip.empty?

    extension = File.extname(image).downcase
    unless SUPPORTED_IMAGE_EXTENSIONS.include?(extension)
      errors << "#{source}: image has unsupported extension: #{image}"
      next
    end

    path = File.expand_path(image.sub(%r{\A/}, ""), root)
    unless path == root || path.start_with?(root + File::SEPARATOR)
      errors << "#{source}: image must stay inside the repository: #{image}"
      next
    end
    unless File.file?(path)
      errors << "#{source}: image file does not exist: #{image}"
      next
    end
    if File.size(path) > MAX_IMAGE_BYTES
      errors << "#{source}: image exceeds 15 MiB: #{image}"
      next
    end

    references[path] << work
  end

  return errors if references.empty?

  stdout, stderr, status = Open3.capture3(
    ENV.fetch("PYTHON", "python3"),
    sanitizer,
    "--check",
    *references.keys.sort
  )
  return errors if status.success?

  reported_paths = (stderr + stdout).lines.map do |line|
    references.keys.find { |path| line.start_with?(path + ":") }
  end.compact.uniq
  reported_paths = references.keys if reported_paths.empty?
  reported_paths.each do |path|
    references[path].each do |work|
      errors << "#{work.fetch('_path', 'work')}: image metadata check failed: #{work['image']}"
    end
  end
  errors
end

options = {}
OptionParser.new do |parser|
  parser.on("--site PATH") { |path| options[:site] = path }
  parser.on("--works DIR") { |path| options[:works] = path }
end.parse!

unless options[:site] && options[:works]
  warn "usage: validate_content.rb --site PATH --works DIR"
  exit 2
end

begin
  site = load_yaml(options[:site])
  works = Dir.glob(File.join(options[:works], "*.md")).sort.map { |path| load_work(path) }
  site_directory = File.dirname(File.expand_path(options[:site]))
  repo_root = File.basename(site_directory) == "_data" ? File.dirname(site_directory) : Dir.pwd
  errors = validate_site(site) + validate_works(works) +
    validate_editor_relationships(site, works) +
    validate_work_images(works, repo_root: repo_root)
rescue ArgumentError => error
  errors = [error.message]
end

if errors.empty?
  puts "content validation: OK"
  exit 0
end

errors.each { |error| warn error }
exit 1
