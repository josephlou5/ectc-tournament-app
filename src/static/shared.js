/**
 * Shared global JavaScript functions.
 */

function ajaxRequest(method, url, options = {}) {
  if (!options.success) {
    options.success = (response, status, jqXHR) => {
      location.reload();
    };
  }
  if (!options.error) {
    options.error = (jqXHR, status, errorThrown) => {
      location.reload();
    };
  }
  // https://api.jquery.com/jquery.ajax/
  $.ajax({ method, url, ...options });
}

function copyElementContent(elementId, callback = null) {
  const text = $('#' + elementId)
    .text()
    .trim();
  navigator.clipboard.writeText(text).then(() => {
    callback?.();
  });
}

// maps: element id -> current timeout
const TIMEOUTS = {};

/**
 * Clears an element after the given amount of seconds.
 */
function clearElementAfter(elementId, seconds = 60) {
  const element = $('#' + elementId);
  if (!element) return;
  // clear any current timeouts
  if (TIMEOUTS[elementId] != null) {
    clearTimeout(TIMEOUTS[elementId]);
    delete TIMEOUTS[elementId];
  }
  if (element.html().trim() !== '') {
    TIMEOUTS[elementId] = setTimeout(() => {
      element.html('');
      if (TIMEOUTS[elementId] != null) {
        delete TIMEOUTS[elementId];
      }
    }, seconds * 1000);
  }
}

/**
 * Sets the text of an element for the given amount of seconds.
 */
function setElementTextFor(elementId, text, seconds = 60) {
  const element = $('#' + elementId);
  element.html(text);
  clearElementAfter(elementId, seconds);
}

function clearInvalid(elementId) {
  $('#' + elementId).removeClass('is-invalid');
  $('#' + elementId + '-invalid').html('');
}

function setInvalid(elementId, message = null) {
  if (message != null) {
    $('#' + elementId + '-invalid').html(message);
  }
  $('#' + elementId).addClass('is-invalid');
}
