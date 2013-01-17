#!/usr/bin/env python
# -*- coding: utf-8 -*-

# First, study the $JOSHUA/scripts/copy-config.pl script for the special
# parameters.

# Example invocation:
'''
$JOSHUA/scripts/support/run-bundler.py \
  --force \
  /home/hltcoe/lorland/expts/haitian-creole-sms/runs/5/test/1/joshua.config \
  /home/hltcoe/lorland/expts/haitian-creole-sms/runs/5 \
  haitian5-bundle \
  --copy-config-options '-top-n 1 -output-format %S -mark-oovs false -server-port 5674 -tm/pt "thrax pt 20 /path/to/copied/unfiltered/grammar.gz"'
'''
# Then, go run the executable file
#   haitian5-bundle/bundle-runner.sh

from __future__ import print_function
import argparse
import os
import re
import shutil
import stat
import sys
from subprocess import check_call, Popen, PIPE

JOSHUA_PATH = os.environ.get('JOSHUA')
FILE_TYPE_TOKENS = set(['lm', 'lmfile', 'tmfile', 'tm', 'weights-file'])
OUTPUT_CONFIG_FILE_NAME = 'joshua.config'
BUNDLE_RUNNER_FILE_NAME = 'run-joshua.sh'
BUNDLE_RUNNER_TEXT = """#!/bin/bash
# Usage: bundle_destdir/%s [extra joshua config options]

bundledir=$(dirname $0)
cd $bundledir   # relative paths are now safe....
$JOSHUA/joshua-decoder -c joshua.config $*
""" % BUNDLE_RUNNER_FILE_NAME


def clear_non_empty_dir(top):
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(top)


def abs_file_path(dir_path, file_token):
        # The path might be relative or absolute, we don't know.
        match_orig_dir_prefix = re.search("^" + dir_path, file_token)
        match_abs_path = re.search("^/", file_token)
        if match_abs_path or match_orig_dir_prefix:
            return file_token
        return os.path.abspath(os.path.join(dir_path, file_token))


def make_dest_dir(dest_dir, overwrite):
    """
    Create the destination directory. Raise an exception if the specified
    directory exists, and overwriting is not requested.
    """
    if os.path.exists(dest_dir) and overwrite:
        clear_non_empty_dir(dest_dir)
    os.mkdir(dest_dir)


def filter_through_copy_config_script(configs, copy_configs):
    """
    configs should be a list.
    copy_configs should be a list.
    """
    cmd = "$JOSHUA/scripts/copy-config.pl " + copy_configs
    p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE)
    result = p.communicate("\n".join(configs))[0]
    return result.splitlines()


class ConfigLine(object):
    """
    Base class for representing a configuration lines. Subclasses of this class
    are meant to deal with files that get copied or processed.
    """

    def __init__(self, line_parts, orig_dir=None, dest_dir=None,
            pack_grammar=None, binarize_kenlm=None):
        self.line_parts = line_parts
        self.orig_dir = orig_dir
        self.dest_dir = dest_dir
        self.pack_grammar = pack_grammar
        self.binarize_kenlm = binarize_kenlm

    def join_command_comment(self, custom_command_parts=None,
                custom_comment=None):
        """
        Merges line_parts to re-form resulting config line.
        If no values are given for the custom_command_parts and custom_comment
        parameters, the original input configuration string is returned.
        """
        if custom_command_parts:
            command = " ".join(custom_command_parts)
        else:
            command = " ".join(self.line_parts["command"])
        if custom_comment:
            comment = custom_comment
        else:
            comment = self.line_parts["comment"]
        if comment:
            comment = "#" + comment
        return " ".join([command, comment]).strip()

    def process(self):
        pass

    def result(self):
        return self.join_command_comment()


class FileConfigLine(ConfigLine):

    def __init__(self, line_parts, orig_dir, dest_dir,
            pack_grammar=None, binarize_kenlm=None):
        ConfigLine.__init__(self, line_parts, orig_dir, dest_dir, pack_grammar,
                binarize_kenlm)
        self.file_token = self.line_parts["command"][-1]
        self.source_file_path = self.__set_source_file_token()

    def __set_source_file_token(self):
        """
        If the path to the file to be copied is relative, then prepend it with
        the origin directory.
        """
        return abs_file_path(self.orig_dir, self.file_token)


class CopyFileConfigLine(FileConfigLine):

    def __init__(self, line_parts, orig_dir, dest_dir, pack_grammar=None,
            binarize_kenlm=None):
        FileConfigLine.__init__(self, line_parts, orig_dir, dest_dir, pack_grammar,
                binarize_kenlm)
        self.dest_file_path = self.__determine_copy_dest_path()

    def __determine_copy_dest_path(self):
        """
        If the path to the file to be copied is relative, then prepend it with
        the destination directory.
        The path might be relative or absolute, we don't know.
        """
        return os.path.abspath(os.path.join(self.dest_dir,
                os.path.basename(self.file_token)))

    def process(self):
        """
        Copy referenced file or directory tree over to the destination
        directory.
        """
        src = self.source_file_path
        dst = self.dest_file_path
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy(src, dst)

    def result(self):
        """
        return the config line, changed if necessary, reflecting the new
        location of the file.
        """
        # Update the config line to reference the changed path.
        # 1) Remove the directories from the path, since the files are
        #    copied to the top level.
        command_parts = self.line_parts["command"]
        command_parts[-1] = os.path.basename(self.dest_file_path)
        # 2) Put back together the configuration line
        return self.join_command_comment(command_parts)


class BinarizeLmFileConfigLine(CopyFileConfigLine):

    def __init__(self, line_parts, orig_dir, dest_dir, pack_grammar=None,
            binarize_kenlm=None):
        CopyFileConfigLine.__init__(self, line_parts, orig_dir, dest_dir, pack_grammar,
                binarize_kenlm)
        self.dest_file_path = self.__determine_copy_dest_path()

    def process(self):
        """
        process referenced file or directory tree over to the destination
        directory.
        """
        src = self.source_file_path
        dst = self.dest_file_path
        script = os.path.join(JOSHUA_PATH, "src/joshua/decoder/ff/lm/kenlm/build_binary")
        cmd = ' '.join([script, src, dst])
        check_call(cmd, shell=True)

    def __determine_copy_dest_path(self):
        """
        If the path to the file to be copied is relative, then prepend it with
        the destination directory.
        The path might be relative or absolute, we don't know.
        """
        file_name = os.path.basename(self.line_parts["command"][-1])
        if file_name.endswith('.gz'):
            self.new_name = re.sub(r'\.gz$', '.kenlm', file_name)
        else:
            self.new_name = file_name + '.kenlm'
        return os.path.abspath(os.path.join(self.dest_dir, self.new_name))

    def result(self):
        """
        return the config line, changed if necessary, reflecting the new
        location of the file.
        """
        # Update the config line to reference the changed path.
        # 1) Remove the directories from the path, since the files are
        #    copied to the top level.
        command_parts = self.line_parts["command"]
        command_parts[-1] = self.new_name
        # 2) Put back together the configuration line
        return self.join_command_comment(command_parts)


class PackGrammarFileConfigLine(CopyFileConfigLine):

    def __init__(self, line_parts, orig_dir, dest_dir, pack_grammar=None,
            binarize_kenlm=None):
        CopyFileConfigLine.__init__(self, line_parts, orig_dir, dest_dir, pack_grammar,
                binarize_kenlm)
        self.dest_file_path = self.__determine_copy_dest_path()

    def process(self):
        """
        process referenced file or directory tree over to the destination
        directory.
        """
        src = self.source_file_path
        dst = self.dest_file_path
        script = os.path.join(JOSHUA_PATH, "scripts/support/grammar-packer.pl")
        cmd = ' '.join([script, src, dst])
        check_call(cmd, shell=True)

    def __determine_copy_dest_path(self):
        """
        If the path to the file to be copied is relative, then prepend it with
        the destination directory.
        The path might be relative or absolute, we don't know.
        """
        file_name = os.path.basename(self.line_parts["command"][-1])
        if file_name.endswith('.gz'):
            self.new_name = re.sub(r'\.gz$', '.packed', file_name)
        else:
            self.new_name = file_name + '.packed'
        return os.path.abspath(os.path.join(self.dest_dir, self.new_name))


    def result(self):
        """
        return the config line, changed if necessary, reflecting the new
        location of the file.
        """
        # Update the config line to reference the changed path.
        # 1) Remove the directories from the path, since the files are
        #    copied to the top level.
        command_parts = self.line_parts["command"]
        command_parts[-1] = self.new_name
        # 2) Put back together the configuration line
        return self.join_command_comment(command_parts)


def extract_line_parts(line):
    """
    Builds a dict containing tokenized command portion and comment portion of a
    config line
    """
    config, hash_char, comment = line.partition('#')
    return {"command": config.split(), "comment": comment}


def config_line_factory(line, args):
    """
    Factory method that instantiates and returns a new object of a ConfigLine
    (sub)class.
    * line is the configuration line.
    * args is a MyParser object.
    """
    line_parts = extract_line_parts(line)
    tokens = line_parts["command"]
    try:
        config_type_token = tokens[0]
    except:
        config_type_token = None
    if config_type_token in FILE_TYPE_TOKENS:
        # This line refers to a file that should be copied or processed.
        # Absolute path to the source file:
        source_file_path = abs_file_path(args.origdir, tokens[-1])
        if tokens[0].startswith("lm") and source_file_path.endswith(".gz"):
            # This is a language model file to be binarized:
            cl = BinarizeLmFileConfigLine(line_parts, args.origdir,
                    args.destdir, args.pack_grammar, args.binarize_kenlm)
            return cl
        if tokens[0].startswith("tm") and not os.path.isdir(source_file_path):
            # This is a translation model file to be packed:
            cl = PackGrammarFileConfigLine(line_parts, args.origdir,
                    args.destdir, args.pack_grammar, args.binarize_kenlm)
            return cl
        # This file doesn't need to be processed, so just copy it:
        cl = CopyFileConfigLine(line_parts, args.origdir, args.destdir,
                args.pack_grammar, args.binarize_kenlm)
        return cl
    else:
        return ConfigLine(line_parts)


def processed_config_line(line, args):
    """
    Factory method that instantiates a new object of a ConfigLine or one of its
    subclasses, runs the object's process() method, and returns the object.
    * line is the configuration line.
    * args is a MyParser object.
    """
    cl = config_line_factory(line, args)
    cl.process()
    return cl


def handle_args(clargs):
    """
    Command-line arguments
    """

    class MyParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)

    # Parse the command line arguments.
    parser = MyParser(description='creates a Joshua configuration bundle from '
                                  'an existing configuration and set of files')
    parser.add_argument('config', type=file,
                        help='path to the origin configuration file. '
                        'e.g. /path/to/test/1/joshua.config.final')
    parser.add_argument('origdir',
                        help='origin directory, which is the root directory '
                        'from which origin files specified by relative paths '
                        'are copied')
    parser.add_argument('destdir',
                        help='destination directory, which should not already '
                        'exist. But if it does, it will be removed if -f is used.')
    parser.add_argument('-f', '--force', action='store_true',
                        help='extant destination directory will be overwritten')
    parser.add_argument('-o', '--copy-config-options',
                        default='',
                        help='optional additional or replacement configuration '
                        'options for Joshua, all surrounded by one pair of '
                        'quotes.')
    parser.add_argument('--pack-grammar',
                        action="store_true",
                        help='use the grammar packer script to pack the '
                        'grammar.')
    parser.add_argument('--binarize-kenlm',
                        nargs='+',
                        help='use the build_binary script to binarize the '
                        'language model(s) listed, for shorter loading at run '
                        'time.')
    return parser.parse_args(clargs)


def main():
    args = handle_args(sys.argv[1:])
    try:
        make_dest_dir(args.destdir, args.force)
    except:
        if os.path.exists(args.destdir) and not args.force:
            sys.stderr.write('error: trying to make existing directory %s\n'
                             % args.destdir)
            sys.stderr.write('use -f or --force option to overwrite the directory.')
            sys.exit(2)
    config_lines = [line.strip() for line in args.config]
    if args.copy_config_options:
        config_lines = filter_through_copy_config_script(config_lines,
                args.copy_config_options)
    # Create the resource files in the new bundle.
    # Some results might be a list of more than one line.
    result_config_lines = [processed_config_line(line.strip(), args).result()
                           for line in config_lines]
    # Create the Joshua configuration file for the package
    with open(os.path.join(args.destdir, OUTPUT_CONFIG_FILE_NAME), 'w') as fh:
        for line in result_config_lines:
            fh.write(line + '\n')
    # Write the script that runs Joshua using the configuration and resources
    # in the bundle.
    with open(os.path.join(args.destdir, BUNDLE_RUNNER_FILE_NAME), 'w') as fh:
        fh.write(BUNDLE_RUNNER_TEXT)
        # The mode will be read and execute by all.
        mode = stat.S_IREAD | stat.S_IEXEC | stat.S_IRGRP | stat.S_IXGRP \
                | stat.S_IROTH | stat.S_IXOTH
        os.chmod(os.path.join(args.destdir, BUNDLE_RUNNER_FILE_NAME), mode)


if __name__ == "__main__":
    main()


######################
##### Unit Tests #####
######################

import unittest
from mock import Mock


class TestRunBundler_cli(unittest.TestCase):

    def test_force(self):
        args = handle_args(["--force",
                            "/dev/null",
                            "/dev/null",
                            "haitian5-bundle"])
        self.assertIsInstance(args.config, file)

    def test_no_force(self):
        args = handle_args(["/dev/null",
                            "/dev/null",
                            "haitian5-bundle"])
        self.assertIsInstance(args.config, file)

    def test_copy_config_options(self):
        """
        For --copy_config_options, Space-separated options surrounded by a pair
        of quotes should not be split.
        """
        args = handle_args(["/dev/null",
                            "/dev/null",
                            "haitian5-bundle",
                            "--copy-config-options",
                            "-grammar grammar.gz"])
        self.assertIsInstance(args.config, file)
        self.assertEqual("-grammar grammar.gz", args.copy_config_options)

    def test_copy_config_options__empty(self):
        """
        An error should result from --copy-config-options with no options.
        """
        with self.assertRaises(SystemExit):
            handle_args(["/dev/null",
                         "/dev/null",
                         "haitian5-bundle",
                         "--copy-config-options"])


class TestRunBundler_bundle_dir(unittest.TestCase):

    def setUp(self):
        self.test_dest_dir = "newdir"
        self.config_line_abs = 'tm = thrax pt 12 /home/hltcoe/lorland/expts/haitian-creole-sms/runs/5/data/test/grammar.filtered.gz'
        self.config_line_rel = 'lm = berkeleylm 5 false false 100 lm.berkeleylm'

        # Create the destination directory an put a file in it.
        if not os.path.exists(self.test_dest_dir):
            os.mkdir(self.test_dest_dir)
        temp_file_path = os.path.join(self.test_dest_dir, 'temp')
        open(temp_file_path, 'w').write('test text')

    def tearDown(self):
        if os.path.exists(self.test_dest_dir):
            clear_non_empty_dir(self.test_dest_dir)
        pass

    def test_clear_non_empty_dir(self):
        clear_non_empty_dir(self.test_dest_dir)
        self.assertFalse(os.path.exists(self.test_dest_dir))

    def test_force_make_dest_dir__extant_not_empty(self):
        # The existing directory should be removed and a new empty directory
        # should be in its place.
        make_dest_dir(self.test_dest_dir, True)
        self.assertTrue(os.path.exists(self.test_dest_dir))
        self.assertEqual([], os.listdir(self.test_dest_dir))

    def test_make_dest_dir__non_extant(self):
        # Set up by removing (existing) directory.
        clear_non_empty_dir(self.test_dest_dir)
        # A new empty directory should be created.
        make_dest_dir(self.test_dest_dir, False)
        self.assertTrue(os.path.exists(self.test_dest_dir))


class TestProcessedConfigLine_blank(unittest.TestCase):

    def setUp(self):
        self.args = handle_args(['/dev/null', '/dev/null', '/dev/null'])

    def test_output_is_input(self):
        """
        The resulting processed config line of a comment line is that same
        comment line.
        """
        cl_object = processed_config_line('', self.args)
        expect = ''
        actual = cl_object.result()
        self.assertEqual(expect, actual)


class TestProcessedConfigLine_comment(unittest.TestCase):

    def setUp(self):
        self.line = '# This is the location of the file containing model weights.'
        self.args = handle_args(['/dev/null', '/dev/null', '/dev/null'])

    def test_line_type(self):
        cl_object = processed_config_line(self.line, self.args)
        self.assertIsInstance(cl_object, ConfigLine)

    def test_output_is_input(self):
        """
        The resulting processed config line of a comment line is that same
        comment line.
        """
        expect = '# This is the location of the file containing model weights.'
        actual = processed_config_line(expect, self.args).result()
        self.assertEqual(expect, actual)


class TestProcessedConfigLine_copy1(unittest.TestCase):

    def setUp(self):
        self.line = 'weights-file = test/parser/weights # foo bar'
        self.args = Mock()
        self.args.origdir = JOSHUA_PATH
        self.args.destdir = '/tmp/testdestdir'
        if os.path.exists(self.args.destdir):
            clear_non_empty_dir(self.args.destdir)
        os.mkdir(self.args.destdir)

    def tearDown(self):
        if os.path.exists(self.args.destdir):
            clear_non_empty_dir(self.args.destdir)

    def test_line_type(self):
        cl_object = processed_config_line(self.line, self.args)
        self.assertIsInstance(cl_object, ConfigLine)

    def test_output_is_input(self):
        """
        The resulting processed config line of a comment line is that same
        comment line.
        """
        expect = '# This is the location of the file containing model weights.'
        actual = processed_config_line(expect, self.args).result()
        self.assertEqual(expect, actual)


class TestProcessedConfigLine_copy2(unittest.TestCase):

    def setUp(self):
        self.line = 'weights-file = test/parser/weights # foo bar'
        args = Mock()
        self.args = args
        args.origdir = JOSHUA_PATH
        args.destdir = './testdestdir'
        self.destdir = args.destdir
        # Create the destination directory.
        if not os.path.exists(args.destdir):
            os.mkdir(args.destdir)
        self.cl_object = processed_config_line(self.line, args)
        self.expected_source_file_path = os.path.abspath(os.path.join(args.origdir,
                    'test', 'parser', 'weights'))
        self.expected_dest_file_path = os.path.abspath(os.path.join(args.destdir, 'weights'))

    def tearDown(self):
        if not os.path.exists(self.destdir):
            os.mkdir(self.destdir)

    def test_line_source_path(self):
        actual = self.cl_object.source_file_path
        self.assertEqual(self.expected_source_file_path, actual)

    def test_line_parts(self):
        cl_object = processed_config_line(self.line, self.args)
        expect = {"command": ['weights-file', '=', 'test/parser/weights'],
                  "comment": '# foo bar'}
        actual = cl_object.line_parts
        self.assertEqual(expect["command"], actual["command"])

    def test_line_dest_path(self):
        actual = self.cl_object.dest_file_path
        self.assertEqual(self.expected_dest_file_path, actual)

    def test_line_copy_file(self):
        self.assertTrue(os.path.exists(self.cl_object.dest_file_path))


class TestProcessedConfigLine_copy_dirtree(unittest.TestCase):

    def setUp(self):
        # N.B. specify a path to copytree that is not inside you application.
        # Otherwise it ends with an infinite recursion.
        self.line = 'tm = thrax pt 12 example # foo bar'
        self.args = Mock()
        self.args.origdir = os.path.join(JOSHUA_PATH, 'examples')
        self.args.destdir = './testdestdir'
        # Create the destination directory.
        if os.path.exists(self.args.destdir):
            clear_non_empty_dir(self.args.destdir)
        os.mkdir(self.args.destdir)

    def tearDown(self):
        if os.path.exists(self.args.destdir):
            clear_non_empty_dir(self.args.destdir)

    def test_line_parts(self):
        cl_object = processed_config_line(self.line, self.args)
        expect = {"command": ['tm', '=', 'thrax', 'pt', '12', 'example'],
                  "comment": '# foo bar'}
        actual = cl_object.line_parts
        self.assertEqual(expect["command"], actual["command"])

    def test_line_copy_dirtree(self):
        processed_config_line(self.line, self.args)
        expect = os.path.join(self.args.destdir, 'example', 'joshua.config')
        self.assertTrue(os.path.exists(expect))

    def test_line_copy_dirtree_result(self):
        cl_object = processed_config_line(self.line, self.args)
        expect = 'tm = thrax pt 12 example # foo bar'
        actual = cl_object.result()
        self.assertEqual(expect, actual)


class TestMain(unittest.TestCase):

    def setUp(self):
        self.line = 'weights-file = weights # foo bar\noutput-format = %1'
        self.origdir = '/tmp/testorigdir'
        self.destdir = '/tmp/testdestdir'
        for d in [self.origdir, self.destdir]:
            if os.path.exists(d):
                clear_non_empty_dir(d)
        # Create the destination directory.
        os.mkdir(self.origdir)
        os.mkdir(self.destdir)
        # Write the files to be processed.
        config_file = os.path.join(self.origdir, 'joshua.config')
        with open(config_file, 'w') as fh:
            fh.write(self.line)
        with open(os.path.join(self.origdir, 'weights'), 'w') as fh:
            fh.write("grammar data\n")
        self.args = ['thisprogram', '-f', config_file, self.origdir,
                     self.destdir]

    def tearDown(self):
        for d in [self.origdir, self.destdir]:
            if os.path.exists(d):
                clear_non_empty_dir(d)

    def test_main(self):
        sys.argv = self.args
        main()
        actual = os.path.exists(os.path.join(self.destdir, 'weights'))
        self.assertTrue(actual)
        with open(os.path.join(self.destdir, 'joshua.config')) as fh:
            actual = fh.read().splitlines()
        expect = ['weights-file = weights # foo bar', 'output-format = %1']
        self.assertEqual(expect, actual)

    def test_main_with_copy_config_options(self):
        """
        For --copy_config_options, Space-separated options surrounded by a pair
        of quotes should not be split.
        """
        sys.argv = self.args + ["--copy-config-options", "-topn 1"]
        main()
        with open(os.path.join(self.destdir, 'joshua.config')) as fh:
            actual = fh.read().splitlines()
        expect = ['weights-file = weights # foo bar', 'output-format = %1',
                  "topn = 1"]
        self.assertEqual(expect, actual)
        self.assertEqual(3, len(actual))


class TestFilterThroughCopyConfigScript(unittest.TestCase):

    def test_method(self):
        expect = ["# hello", "topn = 1"]
        actual = filter_through_copy_config_script(["# hello"], "-topn 1")
        self.assertEqual(expect, actual)


class TestBinarizeLmFileConfigLine_process_lm_binarize(unittest.TestCase):

    def setUp(self):
        self.line = "lm = kenlm 5 false false 100 lm.gz"
        self.origdir = os.path.join(JOSHUA_PATH, 'test/bn-en/hiero')
        self.destdir = '/tmp/testdestdir'
        # Create the destination directory.
        if os.path.exists(self.destdir):
            clear_non_empty_dir(self.destdir)
        os.mkdir(self.destdir)
        self.args = Mock()
        self.args.origdir = self.origdir
        self.args.destdir = self.destdir

    def tearDown(self):
        if os.path.exists(self.destdir):
            clear_non_empty_dir(self.destdir)

    def test_cl_object(self):
        cl_object = processed_config_line(self.line, self.args)
        self.assertIsInstance(cl_object, BinarizeLmFileConfigLine)

    def test_file_name(self):
        line_parts = extract_line_parts(self.line)
        cl_object = BinarizeLmFileConfigLine(line_parts, self.origdir,
                self.destdir, None, None)
        expect = 'lm = kenlm 5 false false 100 lm.kenlm'
        actual = cl_object.result()
        self.assertEqual(expect, actual)

    def test_line_grammar_lm_binarizer_process(self):
        line_parts = extract_line_parts(self.line)
        cl_object = BinarizeLmFileConfigLine(line_parts, self.origdir,
                self.destdir, None, None)
        cl_object.process()
        expect = os.path.join(self.destdir, 'lm.kenlm')
        self.assertTrue(os.path.exists(expect))
        orig_size = os.path.getsize(os.path.join(self.origdir, 'lm.gz'))
        dest_size = os.path.getsize(os.path.join(self.destdir, 'lm.kenlm'))
        self.assertTrue(dest_size > orig_size)


class TestBinarizeLmFileConfigLine_process_lmfile_binarize(unittest.TestCase):

    def setUp(self):
        self.origdir = os.path.join(JOSHUA_PATH, 'test', 'bn-en', 'hiero')
        self.destdir = '/tmp/testdestdir'
        self.config_line = 'lmfile = lm.gz'
        self.expect = 'lmfile = lm.kenlm'

    def test_line_lmfile_deprecated_statement__class(self):
        cl_object = \
                BinarizeLmFileConfigLine(extract_line_parts(self.config_line),
                        self.origdir, self.destdir, None, None)
        actual = cl_object.result()
        self.assertEqual(self.expect, actual)

    def test_line_lmfile_deprecated_statement__factory(self):
        """
        Processed_config_line should properly detect this unbinarized lm file.
        """
        args = Mock()
        args.origdir = self.origdir
        args.destdir = self.destdir
        cl_object = config_line_factory(self.config_line, args)
        self.assertIsInstance(cl_object, BinarizeLmFileConfigLine)
        actual = cl_object.result()
        self.assertEqual(self.expect, actual)


class TestBinarizeLmFileConfigLine_process_lm_binarize_2(unittest.TestCase):

    def setUp(self):
        self.args = Mock()
        self.args.origdir = os.path.join(JOSHUA_PATH, 'test/bn-en/hiero')
        self.args.destdir = '/tmp/testdestdir'
        self.line = 'something = lm.gz'

    def test_line_not_lm_instance(self):
        '''
        The method should not detect this as a lm file and create a
        BinarizeLmFileConfigLine object
        '''
        cl_object = processed_config_line(self.line, self.args)
        self.assertNotIsInstance(cl_object, BinarizeLmFileConfigLine)

    def test_line_not_lm_result(self):
        '''
        The method should not detect this as a lm file and binarize the file.
        '''
        cl_object = config_line_factory(self.line, self.args)
        expect = 'something = lm.gz'
        actual = cl_object.result()
        self.assertEqual(expect, actual)


class TestPackGrammarFileConfigLine(unittest.TestCase):

    def setUp(self):
        self.line = 'tm = thrax pt 12 grammar.gz # foo bar'
        self.line_parts = {'command': 'tm = thrax pt 12 grammar.gz'.split(),
                           'comment': ' foo bar'}
        self.origdir = os.path.join(JOSHUA_PATH, 'test/bn-en/hiero')
        self.destdir = '/tmp/testdestdir'
        # Create the destination directory.
        if os.path.exists(self.destdir):
            clear_non_empty_dir(self.destdir)
        os.mkdir(self.destdir)
        self.args = Mock()
        self.args.origdir = self.origdir
        self.args.destdir = self.destdir

    def tearDown(self):
        if os.path.exists(self.destdir):
            clear_non_empty_dir(self.destdir)

    def test_cl_object(self):
        cl_object = processed_config_line(self.line, self.args)
        self.assertIsInstance(cl_object, PackGrammarFileConfigLine)

    def test_file_name(self):
        cl_object = PackGrammarFileConfigLine(self.line_parts, self.origdir,
                self.destdir, None, None)
        expect = 'tm = thrax pt 12 grammar.packed # foo bar'
        actual = cl_object.result()
        self.assertEqual(expect, actual)

    def test_packed_grammar_is_directory(self):
        """
        The resulting grammar.packed should be a directory.
        """
        cl_object = PackGrammarFileConfigLine(self.line_parts, self.origdir,
                self.destdir, None, None)
        cl_object.process()
        expect = os.path.join(self.destdir, 'grammar.packed')
        self.assertTrue(os.path.isdir(expect))


class TestPackGrammarFileConfigLine_different_name(unittest.TestCase):

    def setUp(self):
        line = 'tm = thrax pt 12 another_grammar # foo bar'
        self.line_parts = extract_line_parts(line)
        self.origdir = '/tmp'
        self.destdir = '/tmp/testdestdir'
        self.grammar_file_path = os.path.join(self.origdir, 'another_grammar')
        if not os.path.exists(self.grammar_file_path):
            with open(self.grammar_file_path, 'w') as fh:
                fh.write('another_grammar')

    def tearDown(self):
        if os.path.exists(self.grammar_file_path):
            os.remove(self.grammar_file_path)

    def test_rename(self):
        '''
        A single-file grammar with a name that doesn't end with .gz should get packed.
        '''
        cl_object = PackGrammarFileConfigLine(self.line_parts, self.origdir,
                self.destdir, None, None)
        line = 'tm = thrax pt 12 another_grammar.packed # foo bar'
        self.assertEqual(line, cl_object.result())


class TestPackGrammarFileConfigLine_dont_pack(unittest.TestCase):
    """
    If the grammar is already packed, don't re-pack it.
    """

    def setUp(self):
        self.line = 'tm = thrax pt 12 grammar.packed # foo bar'
        self.origdir = '/tmp/testorigdir'
        self.destdir = '/tmp/testdestdir'
        for d in [self.origdir, self.destdir]:
            if os.path.exists(d):
                clear_non_empty_dir(d)
        # Create the destination directory.
        os.mkdir(self.origdir)
        os.mkdir(os.path.join(self.origdir, 'grammar.packed'))
        os.mkdir(self.destdir)
        self.args = Mock()
        self.args.origdir = self.origdir
        self.args.destdir = self.destdir

    def tearDown(self):
        for d in [self.origdir, self.destdir]:
            if os.path.exists(d):
                clear_non_empty_dir(d)

    def test_instance(self):
        '''
        The method should not detect this as a tm file that needs to be packed.
        '''
        cl_object = processed_config_line(self.line, self.args)
        self.assertNotIsInstance(cl_object, PackGrammarFileConfigLine)
        self.assertIsInstance(cl_object, CopyFileConfigLine)

    def test_result(self):
        '''
        The method should not detect this as a tm file that needs to be packed.
        '''
        cl_object = processed_config_line(self.line, self.args)
        self.assertEqual(self.line, cl_object.result())

    def test_copy(self):
        '''
        The method should not detect this as a tm file that needs to be packed.
        '''
        processed_config_line(self.line, self.args)
        actual = os.path.isdir(os.path.join(self.destdir, 'grammar.packed'))
        self.assertTrue(actual)


class TestAbsFilePath(unittest.TestCase):

    def test_abs_file_path_path_in_file_token_1(self):
        """
        A file token that is already an absolute path outside the origdir should not be changed.
        """
        dir_path = '/foo'
        file_token = '/bar/file.txt'
        expect = file_token
        actual = abs_file_path(dir_path, file_token)
        self.assertEqual(expect, actual)

    def test_abs_file_path_path_in_file_token_2(self):
        """
        A file token that is already an absolute path inside the origdir should not be changed.
        """
        dir_path = '/bar'
        file_token = '/bar/file.txt'
        expect = file_token
        actual = abs_file_path(dir_path, file_token)
        self.assertEqual(expect, actual)

    def test_rel_file_path_path_in_file_token_2(self):
        """
        Relative file path should get the dir_path prepended.
        """
        dir_path = '/foo'
        file_token = 'bar/file.txt'
        expect = '/foo/bar/file.txt'
        actual = abs_file_path(dir_path, file_token)
        self.assertEqual(expect, actual)


# todo
# DONE: copying directories
# DONE: all resulting paths in configurations in bundle should be relative.
# DONE: test copy_config_options
# : prevent more than one input file with the same name from clashing in the
# bundle.
#      from collections import defaultdict
#      file_name_cnts = defaultdict(int)
#      FileConfigLine.file_name_cnts["lm.kenlm"]
#      FileConfigLine.file_name_cnts["grammar.packed"]
# DONE: any lm file ending with gz gets binarized
#   tokens[0] == "lm" and tokens[-1] == "*.gz"
# DONE: any tm file that's not a directory gets packed
