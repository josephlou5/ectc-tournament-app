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

/** MISC **/

function trim(value) {
  return value?.trim() ?? '';
}

function elementHasAttr($element, attrName) {
  return $element.attr(attrName) != null;
}

function getElementAttr($element, attrName) {
  return trim($element.attr(attrName));
}

function getAttr(elementId, attrName) {
  return getElementAttr($('#' + elementId), attrName);
}

function getElementText($element) {
  return trim($element.text());
}

function getText(elementId) {
  return getElementText($('#' + elementId));
}

function copyElementContent(elementId, callback = null) {
  const text = getText(elementId);
  navigator.clipboard.writeText(text).then(() => {
    callback?.();
  });
}

function toggleDisplay(
  $toggleElement,
  $toggleButton,
  { show = 'Show', hide = 'Hide', forceShow = null }
) {
  const isHidden = $toggleElement.hasClass('d-none');
  if (isHidden) {
    if (forceShow === false) {
      // stay hidden
    } else {
      // show
      $toggleElement.removeClass('d-none');
      $toggleButton.text(hide);
    }
  } else {
    if (forceShow === true) {
      // stay shown
    } else {
      // hide
      $toggleElement.addClass('d-none');
      $toggleButton.text(show);
    }
  }
}

/** TIMEOUTS **/

// maps: element id -> current timeout
const TIMEOUTS = {};

function clearElement(elementId) {
  $('#' + elementId).html('');
}

/**
 * Clears an element after the given amount of seconds.
 */
function clearElementAfter(elementId, seconds = 60) {
  if (elementId === '') {
    console.log('clearElementAfter(): Error: empty element id given');
    return;
  }
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
  if (getElementText($element) === '') return;
  TIMEOUTS[elementId] = setTimeout(() => {
    clearElement(elementId);
    if (TIMEOUTS[elementId] != null) {
      delete TIMEOUTS[elementId];
    }
  }, seconds * 1000);
}

/**
 * Sets the text of an element for the given amount of seconds.
 */
function setElementHtmlFor(elementId, text, seconds = 60) {
  $('#' + elementId).html(text);
  clearElementAfter(elementId, seconds);
}

/** FORMS **/

function getInputValue(elementId) {
  const $element = $('#' + elementId);
  if (getElementAttr($element, 'type') === 'checkbox') {
    return $element.prop('checked');
  }
  return trim($element.val());
}

function getRadioInputs(elementName) {
  return $(`input[type="radio"][name="${elementName}"]`);
}

function getRadioValue(elementName) {
  let value = null;
  getRadioInputs(elementName).each((index, element) => {
    const $element = $(element);
    if ($element.prop('checked')) {
      value = trim($element.val());
      return false;
    }
  });
  return value;
}

function clearInvalid(elementId) {
  $('#' + elementId).removeClass('is-invalid');
  clearElement(elementId + '-invalid');
}

/**
 * Given the id of an input element, sets the text of its '.invalid-feedback'
 * element, which is assumed to have the id "#{elementId}-invalid", and marks
 * the input as invalid.
 */
function setInvalid(elementId, message = null) {
  if (message != null) {
    $('#' + elementId + '-invalid').text(message);
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
    $buttonText.text(getElementAttr($buttonText, 'loading'));
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
    $buttonText.text(getElementAttr($buttonText, 'waiting'));
  }
  // enable the button
  $('#' + elementId).prop('disabled', false);
}

/** BOOTSTRAP **/

function enableBsTooltips() {
  $('[data-bs-toggle="tooltip"]').each((index, element) => {
    const tooltip = new bootstrap.Tooltip(element);
  });
}

function _bsAlert(text, accent, textId, tag, small, dismissible) {
  const textIdAttrStr = textId == null ? '' : `id="${textId}"`;
  const dismissibleClass = dismissible ? 'alert-dismissible fade show' : '';
  const sizingClass = small ? 'alert-sm' : 'd-flex mb-2';
  const closeButton = `
    <button
      type="button"
      class="btn-close"
      data-bs-dismiss="alert"
      aria-label="Close"
    ></button>`;
  return `
  <${tag}
    class="alert alert-${accent} ${dismissibleClass} ${sizingClass}"
    role="alert"
  >
    <span ${textIdAttrStr} ${!small ? 'class="me-auto"' : ''}>
      ${text}
    </span>
    ${dismissible ? closeButton : ''}
  </${tag}>`;
}

function bsAlert(
  text,
  accent,
  { textId = null, tag = 'div', dismissible = true } = {}
) {
  return _bsAlert(text, accent, textId, tag, false, dismissible);
}

function bsAlertSm(
  text,
  accent,
  { textId = null, tag = 'span', dismissible = true } = {}
) {
  return _bsAlert(text, accent, textId, tag, true, dismissible);
}

function handleBsPagination(
  allBtnId,
  pageBtnClass,
  pageBtnWrapperClass,
  attr,
  itemClass,
  {
    startCallback = null,
    shouldShowItemCallback = null,
    hideItemCallback = null,
    doneCallback = null,
  } = {}
) {
  if (shouldShowItemCallback == null) {
    shouldShowItemCallback = (selected, $element, environ, defaultShow) =>
      defaultShow;
  }

  function handlePagination(selected = null) {
    if (selected != null && selected === '') return;
    const allBtnClicked = selected == null;
    const environ = {
      allBtnId,
      pageBtnClass,
      pageBtnWrapperClass,
      attr,
      itemClass,
      allBtnClicked,
    };
    startCallback?.(environ);

    if (allBtnClicked) {
      // deactivate all pagination buttons
      $('.' + pageBtnWrapperClass).removeClass('active');
      // activate the "all" pagination button
      $('#' + allBtnId).addClass('active');
    } else {
      // activate only the proper pagination button
      $('.' + pageBtnWrapperClass).each((index, element) => {
        const $btnWrapper = $(element);
        if (getElementAttr($btnWrapper, attr) === selected) {
          $btnWrapper.addClass('active');
        } else {
          $btnWrapper.removeClass('active');
        }
      });
    }
    // show only the proper items
    $('.' + itemClass).each((index, element) => {
      const $element = $(element);
      const defaultShow =
        allBtnClicked || getElementAttr($element, attr) === selected;
      if (shouldShowItemCallback(selected, $element, environ, defaultShow)) {
        $element.removeClass('d-none');
      } else {
        $element.addClass('d-none');
        hideItemCallback?.($element, environ);
      }
    });

    doneCallback?.(environ);
  }

  // initialize with everything showing
  handlePagination();
  $('.' + pageBtnClass).click((event) => {
    const $pageBtn = $(event.target);
    if (elementHasAttr($pageBtn, 'all-' + attr)) {
      // "all" button clicked
      handlePagination();
    } else {
      handlePagination(getElementText($pageBtn));
    }
  });
}
