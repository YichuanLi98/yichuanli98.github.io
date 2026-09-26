#!/usr/bin/env ruby

require "date"
require "optparse"
require "yaml"

SITE_KEYS = %w[owner seo navigation hero sections footer contact].freeze
WORK_KEYS = %w[title category image alt description location date order featured visible].freeze
WORK_CATEGORIES = %w[photography painting].freeze

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
  errors
end

def validate_works(works)
  errors = []
  works.each do |work|
    path = work.fetch("_path", "work")
    missing = WORK_KEYS.reject { |key| work.key?(key) }
    errors << "#{path}: missing fields: #{missing.join(', ')}" unless missing.empty?

    %w[title image alt].each do |field|
      value = work[field]
      errors << "#{path}: #{field} must not be empty" unless value.is_a?(String) && !value.strip.empty?
    end

    unless WORK_CATEGORIES.include?(work["category"])
      errors << "#{path}: category must be photography or painting"
    end
    errors << "#{path}: order must be an integer" unless work["order"].is_a?(Integer)
    errors << "#{path}: featured must be true or false" unless [true, false].include?(work["featured"])
    errors << "#{path}: visible must be true or false" unless [true, false].include?(work["visible"])
  end

  works.group_by { |work| [work["category"], work["order"]] }.each do |(category, order), entries|
    next if order.nil? || entries.length == 1

    paths = entries.map { |entry| entry.fetch("_path", "work") }.join(", ")
    errors << "#{paths}: duplicate order #{order} in #{category}"
  end

  visible_photos = works.select { |work| work["category"] == "photography" && work["visible"] == true }
  errors << "works: at least one visible photograph is required" if visible_photos.empty?

  featured_photos = visible_photos.select { |work| work["featured"] == true }
  if featured_photos.length != 1
    errors << "works: exactly one visible featured photograph is required (found #{featured_photos.length})"
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
  errors = validate_site(site) + validate_works(works)
rescue ArgumentError => error
  errors = [error.message]
end

if errors.empty?
  puts "content validation: OK"
  exit 0
end

errors.each { |error| warn error }
exit 1
