# -*- coding: UTF-8 -*-
# pylint: disable=line-too-long
"""
Gherkin parser with `Gherkin v6 grammar`_ (and Gherkin v5 or older).

Gherkin v6 grammar extensions:

* Rule keyword added
* Aliases for Scenario, ScenarioOutline to better correspond to `Example Mapping`_

A Rule (or: business rule) allows to group multiple Scenarios::

    # -- RULE GRAMMAR PSEUDO-CODE:
    @tag1 @tag2
    Rule: Optional Rule Title...
        Description?        #< CARDINALITY: 0..1 (optional)
        Background?         #< CARDINALITY: 0..1 (optional)
        Scenario*           #< CARDINALITY: 0..N (many)
        ScenarioOutline*    #< CARDINALITY: 0..N (many)

Keyword aliases:

    | Concept          | Gherkin v6         | Alias (Gherkin v5) |
    | Scenario         | Example            | Scenario           |
    | Scenario Outline | Scenario Template  | Scenario Outline   |

.. seealso::

    * `Gherkin v6 grammar`_

    EXAMPLE MAPPING:

    * Cucumber: `Example Mapping`_
    * Cucumber: `Example Mapping Webinar`_
    * https://docs.cucumber.io/bdd/example-mapping/

.. _`Gherkin v6 grammar`: https://github.com/cucumber/cucumber/blob/master/gherkin/gherkin.berp
.. _`Example Mapping`: https://cucumber.io/blog/example-mapping-introduction/
.. _`Example Mapping Webinar`: https://cucumber.io/blog/example-mapping-webinar/
"""
# pylint: enable=line-too-long

from __future__ import absolute_import, with_statement
import logging
import re
import sys
import six
from behave import model, i18n
from behave.textutil import text as _text


DEFAULT_LANGUAGE = "en"


def parse_file(filename, language=None):
    with open(filename, "rb") as f:
        # file encoding is assumed to be utf8. Oh, yes.
        data = f.read().decode("utf8")
    return parse_feature(data, language, filename)


def parse_feature(data, language=None, filename=None):
    # ALL data operated on by the parser MUST be unicode
    assert isinstance(data, six.text_type)

    try:
        result = Parser(language).parse(data, filename)
    except ParserError as e:
        e.filename = filename
        raise

    return result


def parse_rule(text, language=None, filename=None):
    """Parse a rule with its background and scenario(s).

    :param text: Multi-line text with rule to parse (as unicode).
    :param language:  i18n language identifier (optional).
    :param filename:  Filename (optional).
    :return: Parsed steps (if successful).
    """
    assert isinstance(text, six.text_type)
    try:
        result = Parser(language, variant="rule").parse_rule(text, filename)
    except ParserError as e:
        e.filename = filename
        raise
    return result

def parse_steps(text, language=None, filename=None):
    """Parse a number of steps a multi-line text from a scenario.
    Scenario line with title and keyword is not provided.

    :param text: Multi-line text with steps to parse (as unicode).
    :param language:  i18n language identifier (optional).
    :param filename:  Filename (optional).
    :return: Parsed steps (if successful).
    """
    assert isinstance(text, six.text_type)
    try:
        result = Parser(language, variant="steps").parse_steps(text, filename)
    except ParserError as e:
        e.filename = filename
        raise
    return result


def parse_step(text, language=None, filename=None):
    """Parse one step as multi-line text.

    :param text: Multi-line text with step to parse (as unicode).
    :param language:  i18n language identifier (optional).
    :param filename:  Filename (optional).
    :return: Parsed step (if successful).
    """
    steps = parse_steps(text, language=language, filename=filename)
    assert len(steps) == 1
    return steps[0]


def parse_tags(text):
    """
    Parse tags from text (one or more lines, as string).

    :param text: Multi-line text with tags to parse (as unicode).
    :return: List of tags (if successful).
    """
    # assert isinstance(text, unicode)
    return [] if not text else Parser(variant="tags").parse_tags(text)


class ParserError(Exception):
    @staticmethod
    def make_annotated(message, line_number, line_text=None, reason=None):
        """Make annotated message enriched w/ line_number, line_text."""
        if line_number:
            message += u" at line %d" % line_number
        if line_text:
            message += f': "{line_text.strip()}"'
        if reason:
            message += u"\nREASON: %s" % reason
        return message

    def __init__(self, message, line, filename=None, line_text=None,
                 reason=None, use_annotated_message=True):
        if use_annotated_message:
            message = self.make_annotated(message, line, line_text, reason)

        super(ParserError, self).__init__(message)
        self.line = line    # Line number of parse failure.
        self.line_text = line_text
        self.filename = filename

    def __str__(self):
        arg0 = _text(self.args[0])
        if self.filename:
            filename = _text(self.filename, sys.getfilesystemencoding())
            return f'Failed to parse "{filename}": {arg0}'
        # -- OTHERWISE:
        return f"Failed to parse <string>: {arg0}"

    if six.PY2:
        __unicode__ = __str__
        __str__ = lambda self: self.__unicode__().encode("utf-8")


class Parser(object):
    """Feature file parser for behave."""
    # pylint: disable=too-many-instance-attributes

    def __init__(self, language=None, variant=None):
        if not variant:
            variant = "feature"
        self.language = language
        self.variant = variant
        self.state = "init"
        self.line = 0
        self.last_step_type = None
        self.multiline_start = None
        self.multiline_leading = None
        self.multiline_terminator = None

        self.filename = None
        self.scenario_container = None  # Feature or Rule.
        self.feature = None
        self.rule = None
        self.parent = None
        self.statement = None
        self.tags = []
        self.lines = []
        self.table = None
        self.examples = None
        self.keywords = None
        if self.language:
            self.keywords = i18n.languages[self.language]
        # NOT-NEEDED: self.reset()

    def reset(self):
        # This can probably go away.
        self.keywords = i18n.languages[self.language] if self.language else None
        self.state = "init"
        self.line = 0
        self.last_step_type = None
        self.multiline_start = None
        self.multiline_leading = None
        self.multiline_terminator = None

        self.filename = None
        self.scenario_container = None  # Feature or Rule.
        self.feature = None
        self.rule = None
        self.parent = None
        self.statement = None
        self.tags = []
        self.lines = []
        self.table = None
        self.examples = None

    def parse(self, text, filename=None):
        self.reset()
        self.filename = filename

        for line in text.split("\n"):
            self.line += 1
            if not line.strip() and self.state != "multiline_text":
                # -- SKIP EMPTY LINES, except in multiline string args.
                continue
            self.action(line)

        if self.table:
            self.action_table("")

        feature = self.feature
        if feature:
            feature.parser = self
        self.reset()
        return feature

    def _build_feature(self, keyword, line):
        name = line[len(keyword) + 1:].strip()
        language = self.language or DEFAULT_LANGUAGE
        feature = model.Feature(self.filename, self.line, keyword, name,
                                tags=self.tags, language=language)
        self.feature = feature
        self.scenario_container = feature
        self.rule = None
        # -- RESET STATE:
        self.tags = []

    def _build_rule_statement(self, keyword, line):
        name = line[len(keyword) + 1:].strip()
        rule = model.Rule(self.filename, self.line, keyword, name,
                          tags=self.tags)
        self.rule = rule
        self.scenario_container = rule
        self.statement = rule
        self.feature.add_rule(self.statement)
        # -- RESET STATE:
        self.tags = []

    def _build_background_statement(self, keyword, line):
        if self.tags:
            msg = f'Background supports no tags: @{" @".join(self.tags)}'
            raise ParserError(msg, self.line, self.filename, line)
        elif self.scenario_container and self.scenario_container.background:
            if self.scenario_container.background.steps:
                # -- HINT: Rule may have default background w/o steps.
                msg = u"Second Background (can have only one)"
                raise ParserError(msg, self.line, self.filename, line)
        name = line[len(keyword) + 1:].strip()
        background = model.Background(self.filename, self.line, keyword, name)
        self.scenario_container.add_background(background)
        self.statement = background

    def _build_scenario_statement(self, keyword, line):
        name = line[len(keyword) + 1:].strip()
        scenario = model.Scenario(self.filename, self.line, keyword, name,
                                  tags=self.tags)
        self.statement = scenario
        self.scenario_container.add_scenario(scenario)
        # OLD: self.feature.add_scenario(self.statement)
        # -- RESET STATE:
        self.tags = []

    def _build_scenario_outline_statement(self, keyword, line):
        # pylint: disable=C0103
        #   C0103   Invalid name "build_scenario_outline_statement", too long.
        name = line[len(keyword) + 1:].strip()
        template = model.ScenarioOutline(self.filename, self.line, keyword, name,
                                         tags=self.tags)
        self.statement = template
        self.scenario_container.add_scenario(template)
        # OLD: self.feature.add_scenario(self.statement)
        # -- RESET STATE:
        self.tags = []

    def _build_examples(self, keyword, line):
        if not isinstance(self.statement, model.ScenarioOutline):
            message = u"Examples must only appear inside scenario outline"
            raise ParserError(message, self.line, self.filename, line)
        name = line[len(keyword) + 1:].strip()
        self.examples = model.Examples(self.filename, self.line,
                                       keyword, name, tags=self.tags)
        # pylint: disable=E1103
        #   E1103   Instance of "Background" has no "examples" member
        #           (but some types could not be inferred).
        self.statement.examples.append(self.examples)

        # -- RESET STATE:
        self.tags = []


    def diagnose_feature_usage_error(self):
        if self.feature:
            return "Multiple features in one file are not supported."
        # -- OTHERWISE:
        return "Feature should not be used here."

    def diagnose_rule_usage_error(self):
        # pylint: disable=no-self-use
        return "Rule should not be used here."

    def diagnose_background_usage_error(self):
        if self.scenario_container and self.scenario_container.scenarios:
            # -- CASE: Feature or Rule
            return "Background may not occur after Scenario/ScenarioOutline."
        elif self.tags:
            return "Background does not support tags."
        # -- OTHERWISE:
        return "Background should not be used here."

    def diagnose_scenario_usage_error(self):
        if not self.scenario_container:
            return "Scenario may not occur before Feature."
        # -- OTHERWISE:
        return "Scenario should not be used here."

    def diagnose_scenario_outline_usage_error(self): # pylint: disable=invalid-name
        if not self.scenario_container:
            return "ScenarioOutline may not occur before Feature."
        # -- OTHERWISE:
        return "ScenarioOutline should not be used here."

    def ask_parse_failure_oracle(self, line):
        """
        Try to find the failure reason when a parse failure occurs:

            Oracle, oracle, ... what went wrong?

        :param line:  Text line where parse failure occured (as string).
        :return: Reason (as string) if an explanation is found.
                 Otherwise, empty string or None.
        """
        if feature_keyword := self.match_keyword("feature", line):
            return self.diagnose_feature_usage_error()
        if rule_keyword := self.match_keyword("rule", line):
            return self.diagnose_rule_usage_error()
        if background_keyword := self.match_keyword("background", line):
            return self.diagnose_background_usage_error()
        if scenario_keyword := self.match_keyword("scenario", line):
            return self.diagnose_scenario_usage_error()
        if scenario_outline_keyword := self.match_keyword(
            "scenario_outline", line
        ):
            return self.diagnose_scenario_outline_usage_error()
        # -- OTHERWISE:
        if self.variant == "feature" and not self.feature:
            return "No feature found."
        # -- FINALLY: No glue what went wrong.
        return None

    def action(self, line):
        if line.strip().startswith("#") and self.state != "multiline_text":
            if self.state != "init" or self.tags or self.variant != "feature":
                return

            # -- DETECT: language comment (at begin of feature file; state=init)
            line = line.strip()[1:].strip()
            if line.lstrip().lower().startswith("language:"):
                language = line[9:].strip()
                self.language = language
                self.keywords = i18n.languages[language]
            return

        func = getattr(self, f"action_{self.state}", None)
        if func is None:
            line = line.strip()
            msg = f"Parser in unknown state {self.state};"
            raise ParserError(msg, self.line, self.filename, line)

        if not func(line):
            line = line.strip()
            msg = u'\nParser failure in state=%s' % self.state
            reason = self.ask_parse_failure_oracle(line)
            raise ParserError(msg, self.line, self.filename,
                              line_text=line, reason=reason)

    def action_init(self, line):
        line = line.strip()
        if line.startswith("@"):
            self.tags.extend(self.parse_tags(line))
            return True

        if feature_keyword := self.match_keyword("feature", line):
            self._build_feature(feature_keyword, line)
            self.state = "feature"
            return True
        return False

    # pylint: disable=invalid-name
    def subaction_detect_taggable_statement(self, line):
        """Subaction is used after first tag line is detected.
        Additional lines with tags or taggable_statement follow.

        Taggable statements (excluding Feature) are:
        * Rule
        * Scenario
        * ScenarioOutline
        * Examples (within ScenarioOutline)
        """
        if line.startswith("@"):
            self.tags.extend(self.parse_tags(line))
            self.state = "taggable_statement"
            return True

        if rule_keyword := self.match_keyword("rule", line):
            # MAYBE: Finish last rule statement
            self._build_rule_statement(rule_keyword, line)
            self.state = "rule"
            return True

        if scenario_keyword := self.match_keyword("scenario", line):
            self._build_scenario_statement(scenario_keyword, line)
            self.state = "scenario"
            return True

        if template_keyword := self.match_keyword("scenario_outline", line):
            self._build_scenario_outline_statement(template_keyword, line)
            self.state = "scenario"
            return True

        if examples_keyword := self.match_keyword("examples", line):
            self._build_examples(examples_keyword, line)
            self.state = "table"
            return True

        # -- OTHERWISE:
        return False
    # pylint: enable=invalid-name

    def action_feature(self, line):
        line = line.strip()
        # OLD: if self.subaction_detect_next_scenario(line):
        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Rule, Scenario, ScenarioOutline (or tags)
            return True

        if background_keyword := self.match_keyword("background", line):
            self._build_background_statement(background_keyword, line)
            self.state = "background"
            return True

        self.feature.description.append(line)
        return True

    def action_taggable_statement(self, line):
        """Entered after first tag for Scenario/ScenarioOutline or
        Examples is detected (= taggable_statement except Feature).

        Taggable statements (excluding Feature) are:
          * Scenario
          * ScenarioOutline
          * Examples (within ScenarioOutline)
        """
        line = line.strip()
        return bool(self.subaction_detect_taggable_statement(line))

    def action_background(self, line):
        """Entered when Background keyword/line is detected.
        Hunts/collects background description lines.

        DETECT:

        * first step of Background
        * next Scenario/ScenarioOutline.
        * any description line after Background keyword
        """
        # -- SAME AS: action_scenario(), only Background is used as self.statement.
        # REUSE: Already existing action.
        return self.action_scenario(line)

    def action_rule(self, line):
        """Entered when Rule keyword/line is detected.
        Hunts/collects rule description lines.

        DETECT:

        * any description line after Rule keyword (optional)
        * Backgroup statement (optional)
        * Scenario/ScenarioOutline statements (many)
        """
        # -- SIMILAR TO: action_feature()
        line = line.strip()
        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Rule, Scenario, ScenarioOutline (or tags)
            return True

        if background_keyword := self.match_keyword("background", line):
            self._build_background_statement(background_keyword, line)
            self.state = "background"
            return True

        self.rule.description.append(line)
        return True


    def action_scenario(self, line):
        """Entered when Scenario/ScenarioOutline keyword/line is detected.
        Hunts/collects scenario description lines.

        DETECT:

        * any description line after Scenario/ScenarioOutline keyword
        * first step of Scenario/ScenarioOutline
        * next Scenario/ScenarioOutline
        """
        self.last_step_type = None
        line = line.strip()
        if step := self.parse_step(line):
            # -- FIRST STEP DETECTED: End collection of description-part.
            self.state = "steps"
            self.statement.steps.append(step)
            return True

        # -- CASE: Detect next Scenario/ScenarioOutline
        #   * Background/Scenario with description, but without steps.
        #   * Title-only Background/Scenario without description and steps.
        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Scenario, ScenarioOutline (or tags)
            return True

        # -- OTHERWISE: Add description line.
        # pylint: disable=E1103
        #   E1103   Instance of "Background" has no "description" member...
        self.statement.description.append(line)
        return True

    def action_steps(self, line):
        """
        Entered when first step is detected (or nested step parsing).

        Subcases:
          * step
          * multi-line text (doc-string), following a step
          * table, following a step
          * examples for a ScenarioOutline, after ScenarioOutline steps

        DETECT:
          * next Scenario/ScenarioOutline or Examples (in a ScenarioOutline)
        """
        # pylint: disable=R0911
        #   R0911   Too many return statements (8/6)
        stripped = line.lstrip()
        # if self.statement.steps:
        #     # -- ENSURE: Multi-line text follows a step.
        #     if stripped.startswith('"""') or stripped.startswith("'''"):
        #         # -- CASE: Multi-line text (docstring) after a step detected.
        #         self.state = "multiline_text"
        #         self.multiline_start = self.line
        #         self.multiline_terminator = stripped[:3]
        #         self.multiline_leading = line.index(stripped[0])
        #         return True

        if stripped.startswith('"""') or stripped.startswith("'''"):
            # -- CASE: Multi-line text (docstring) after a step detected.
            # REQUIRE: Multi-line text follows a step.
            if not self.statement.steps:
                raise ParserError("Multi-line text before any step",
                                  self.line, self.filename)

            self.state = "multiline_text"
            self.multiline_start = self.line
            self.multiline_terminator = stripped[:3]
            self.multiline_leading = line.index(stripped[0])
            return True

        line = line.strip()
        if step := self.parse_step(line):
            self.statement.steps.append(step)
            return True

        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Scenario, ScenarioOutline or Examples (or tags)
            return True

        if line.startswith("|"):
            # -- CASE: TABLE-START detected for data-table of a step
            # OLD: assert self.statement.steps, "TABLE-START without step detected"
            if not self.statement.steps:
                raise ParserError("TABLE-START without step detected",
                                  self.line, self.filename)
            self.state = "table"
            return self.action_table(line)

        return False

    def action_multiline_text(self, line):
        """Parse remaining multi-line/docstring text below a step
        after the triple-quotes were detected:

        * triple-double-quotes or
        * triple-single-quotes

        Leading and trailing triple-quotes must be the same.

        :param line:  Parsed line, as part of a multi-line text (as string).
        """
        if line.strip().startswith(self.multiline_terminator):
            # -- CASE: Handle the end of a multi-line text part.
            # Store the multi-line text in the step object (and continue).
            this_step = self.statement.steps[-1]
            text = u"\n".join(self.lines)
            this_step.text = model.Text(text, u"text/plain", self.multiline_start)
            if this_step.name.endswith(":"):
                this_step.name = this_step.name[:-1]

            # -- RESET INTERNALS: For next step
            self.lines = []
            self.multiline_terminator = None
            self.state = "steps"    # NEXT-STATE: Accept additional step(s).
            return True

        # -- SPECIAL CASE: Strip trailing whitespace (whitespace normalization).
        # HINT: Required for Windows line-endings, like "\r\n", etc.
        text_line = line[self.multiline_leading:].rstrip()
        self.lines.append(text_line)

        # -- BETTER DIAGNOSTICS: May remove non-whitespace in execute_steps()
        removed_line_prefix = line[:self.multiline_leading]
        if removed_line_prefix.strip():
            message = u"BAD-INDENT in multiline text: "
            message += f"Line '{line}' would strip leading '{removed_line_prefix}'"
            raise ParserError(message, self.line, self.filename)
        return True

    def action_table(self, line):
        """Parse a table, with pipe-separated columns:

        * Data table of a step (after the step line)
        * Examples table of a ScenarioOutline
        """
        line = line.strip()
        if not line.startswith("|"):
            # -- CASE: End-of-table detected
            if self.examples:
                # -- CASE: Examples table of a ScenarioOutline
                self.examples.table = self.table
                self.examples = None
            else:
                # -- CASE: Data table of a step
                step = self.statement.steps[-1]
                step.table = self.table
                if step.name.endswith(":"):
                    step.name = step.name[:-1]

            # -- RESET: Parameters for parsing the next step(s).
            self.table = None
            self.state = "steps"
            return self.action_steps(line)

        if not re.match(r"^(|.+)\|$", line):
            logger = logging.getLogger("behave")
            logger.warning(u"Malformed table row at %s: line %i",
                           self.feature.filename, self.line)

        # -- SUPPORT: Escaped-pipe(s) in Gherkin cell values.
        #    Search for pipe(s) that are not preceeded with an escape char.
        cells = [cell.replace("\\|", "|").strip()
                 for cell in re.split(r"(?<!\\)\|", line[1:-1])]
        if self.table is None:
            # -- CASE: First row of the table
            self.table = model.Table(cells, self.line)
        elif len(cells) == len(self.table.headings):
            self.table.add_row(cells, self.line)
        else:
            raise ParserError(u"Malformed table", self.line, self.filename)
        return True

    def match_keyword(self, keyword, line):
        if not self.keywords:
            self.language = DEFAULT_LANGUAGE
            self.keywords = i18n.languages[DEFAULT_LANGUAGE]
        return next(
            (
                alias
                for alias in self.keywords[keyword]
                if line.startswith(f"{alias}:")
            ),
            False,
        )

    def parse_rule(self, text, filename=None):
        """Parse rule with optional background and scenario(s).

        :param text:  Text that contains 0..* steps
        :return: List of parsed rule (as :class:`~behave.model:Rule` object).
        """
        assert isinstance(text, six.text_type)
        if not self.language:
            self.language = DEFAULT_LANGUAGE
        self.reset()
        self.filename = filename
        self.rule = model.Rule(filename, 0, u"rule", u"")
        self.statement = self.rule
        self.state = "rule"

        for line in text.split("\n"):
            self.line += 1
            if not line.strip() and self.state != "multiline_text":
                # -- SKIP EMPTY LINES, except in multiline string args.
                continue
            self.action(line)

        # -- FINALLY:
        if self.table:
            self.action_table("")
        steps = self.statement.steps
        return steps

    def parse_tags(self, line):
        """Parse a line with one or more tags:

          * A tag starts with the AT sign.
          * A tag consists of one word without whitespace chars.
          * Multiple tags are separated with whitespace chars
          * End-of-line comment is stripped.

        :param line:   Line with one/more tags to process.
        :raise ParserError: If syntax error is detected.
        """
        assert line.startswith("@")
        tags = []
        for word in line.split():
            if word.startswith("@"):
                tags.append(model.Tag(word[1:], self.line))
            elif word.startswith("#"):
                break   # -- COMMENT: Skip rest of line.
            else:
                # -- BAD-TAG: Abort here.
                message = f"tag: {word} (line: {line})"
                raise ParserError(message, self.line, self.filename)
        return tags

    def parse_step(self, line):
        for step_type in ("given", "when", "then", "and", "but"):
            for kw in self.keywords[step_type]:
                # try to match the keyword; also attempt a purely lowercase
                # match if that'll work
                if not (line.startswith(kw) or
                        line.lower().startswith(kw.lower())):
                    # -- CASE: Line does not start w/ a step-keyword.
                    continue
                # -- HINT: Trailing SPACE is used for most keywords.
                # BUT: Keywords in some languages (like Chinese, Japanese, ...)
                #      do not need a whitespace as word separator.
                step_text_after_keyword = line[len(kw):].strip()
                if kw.startswith("*") and self.last_step_type:
                    # -- CASE: Generic steps and Given/When/Then steps are mixed.
                    # HINT: Inherit step type from last step.
                    step_type = self.last_step_type
                elif step_type in ("and", "but"):
                    if not self.last_step_type:
                        raise ParserError(u"No previous step",
                                          self.line, self.filename)
                    step_type = self.last_step_type
                else:
                    self.last_step_type = step_type

                keyword = kw.rstrip()  # HINT: Strip optional trailing SPACE.
                return model.Step(
                    self.filename,
                    self.line,
                    keyword,
                    step_type,
                    step_text_after_keyword,
                )
        return None

    def parse_steps(self, text, filename=None):
        """Parse support for execute_steps() functionality that
        supports step with:

        * multiline text
        * table

        :param text:  Text that contains 0..* steps
        :return: List of parsed steps (as model.Step objects).
        """
        assert isinstance(text, six.text_type)
        if not self.language:
            self.language = DEFAULT_LANGUAGE
        self.reset()
        self.filename = filename
        self.statement = model.Scenario(filename, 0, u"scenario", u"")
        self.state = "steps"

        for line in text.split("\n"):
            self.line += 1
            if not line.strip() and self.state != "multiline_text":
                # -- SKIP EMPTY LINES, except in multiline string args.
                continue
            self.action(line)

        # -- FINALLY:
        if self.table:
            self.action_table("")
        steps = self.statement.steps
        return steps
