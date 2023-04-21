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
  const $element = $('#' + elementId);
  if (getElementAttr($element, 'type') === 'checkbox') {
    return $element.prop('checked');
  }
  return $element.val()?.trim() ?? '';
}

function getRadioInputs(elementName) {
  return $(`input[type="radio"][name="${elementName}"]`);
}

function getRadioValue(elementName) {
  let value = null;
  getRadioInputs(elementName).each((index, element) => {
    const $element = $(element);
    if ($element.prop('checked')) {
      value = $element.val()?.trim() ?? '';
      return false;
    }
  });
  return value;
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
    $buttonText.html(getElementAttr($buttonText, 'loading'));
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
    $buttonText.html(getElementAttr($buttonText, 'waiting'));
  }
  // enable the button
  $('#' + elementId).prop('disabled', false);
}

/** MISC **/

function getElementAttr($element, attrName) {
  return $element.attr(attrName)?.trim() ?? '';
}

function getAttr(elementId, attrName) {
  return getElementAttr($('#' + elementId), attrName);
}

function elementHasAttr($element, attrName) {
  return $element.attr(attrName) != null;
}

function copyElementContent(elementId, callback = null) {
  const text = $('#' + elementId)
    .text()
    .trim();
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
      $toggleButton.html(hide);
    }
  } else {
    if (forceShow === true) {
      // stay shown
    } else {
      // hide
      $toggleElement.addClass('d-none');
      $toggleButton.html(show);
    }
  }
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
      handlePagination($pageBtn.html()?.trim() ?? '');
    }
  });
}
