/**
 * Shared global JavaScript functions.
 */

/** JQUERY **/

$.fn.onEnterKeyPress = function (func) {
  const ENTER_KEY = 13;
  return this.each(function () {
    $(this).on('keypress', (event) => {
      if (event.which === ENTER_KEY) {
        func(event);
      }
    });
  });
};

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

/** TIMEOUTS **/

// maps: element id -> current timeout
const TIMEOUTS = {};

/**
 * Clears an element after the given amount of seconds.
 */
function clearElementAfter(elementId, seconds = 60) {
  const $element = $('#' + elementId);
  if ($element.length == 0) {
    console.log('clearElementAfter(): Error: element not found: #' + elementId);
    return;
  }
  // clear any current timeouts
  if (TIMEOUTS[elementId] != null) {
    clearTimeout(TIMEOUTS[elementId]);
    delete TIMEOUTS[elementId];
  }
  // if the element has text, clear it after the specified time
  if ($element.html().trim() === '') return;
  TIMEOUTS[elementId] = setTimeout(() => {
    const $element = $('#' + elementId);
    if ($element.length > 0) {
      $element.html('');
    }
    if (TIMEOUTS[elementId] != null) {
      delete TIMEOUTS[elementId];
    }
  }, seconds * 1000);
}

/**
 * Sets the text of an element for the given amount of seconds.
 */
function setElementTextFor(elementId, text, seconds = 60) {
  $('#' + elementId).html(text);
  clearElementAfter(elementId, seconds);
}

/** FORMS **/

function getInputValue(elementId) {
  return $('#' + elementId)
    .val()
    .trim();
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

/** LOADING BUTTONS **/

function isButtonLoading(elementId) {
  // if the spinner is not hidden, it is loading
  return !$('#' + elementId + '-spinner').hasClass('d-none');
}

function setButtonLoading(elementId) {
  // disable the button
  $('#' + elementId).prop('disabled', true);
  // set the button text, if possible
  const $buttonText = $('#' + elementId + '-text');
  if ($buttonText.length > 0) {
    $buttonText.html($buttonText.attr('loading'));
  }
  // show the spinner
  $('#' + elementId + '-spinner').removeClass('d-none');
}

function stopButtonLoading(elementId) {
  // hide the spinner
  $('#' + elementId + '-spinner').addClass('d-none');
  // set the button text, if possible
  const $buttonText = $('#' + elementId + '-text');
  if ($buttonText.length > 0) {
    $buttonText.html($buttonText.attr('waiting'));
  }
  // enable the button
  $('#' + elementId).prop('disabled', false);
}

/** MISC **/

function getAttr(elementId, attrName) {
  return (
    $('#' + elementId)
      .attr(attrName)
      ?.trim() ?? ''
  );
}

function copyElementContent(elementId, callback = null) {
  const text = $('#' + elementId)
    .text()
    .trim();
  navigator.clipboard.writeText(text).then(() => {
    callback?.();
  });
}

function bsAlertSm(text, accent, tag = 'span') {
  return `
  <${tag}
    class="alert alert-sm alert-${accent} alert-dismissible fade show"
    role="alert"
  >
    ${text}
    <button
      type="button"
      class="btn-close"
      data-bs-dismiss="alert"
      aria-label="Close"
    ></button>
  </${tag}>`;
}
