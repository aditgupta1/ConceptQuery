from .textrank import extract_top_terms

import nltk
import json
import os
import spacy
import pkg_resources

class Parser(object):
    def __init__(self):
        self.terms = None

        gpu = spacy.prefer_gpu()
        if gpu:
            print('GPU activated successfully!')

        self.nlp = spacy.load("en_core_web_sm")
        self.entity_ruler = spacy.pipeline.EntityRuler(self.nlp)
        self.nlp.add_pipe(self.entity_ruler, before='ner')
        self.ruler_patterns_set = set([])

        # Get stopwords
        self.stopwords = set(nltk.corpus.stopwords.words('english'))

        # Get plural to singular file
        lib_path = pkg_resources.resource_filename('concept_query.text_parser', 'lib')
        with open(os.path.join(lib_path, 'plural_to_singular.json'), 'r') as f:
            self.plural_to_singular = json.load(f)

    def extract_terms(self, text, patterns=[]):
        """
        Extracts keywords/phrases given string text
        args:
            text: string
            patterns: new patterns
        returns:
            list of top terms
            store_patterns: patterns to store in database
            freq_data: hit frequency for all entities parsed from page
        """
<<<<<<< HEAD
        self.terms, self.nlp, self.entity_ruler, self.ruler_patterns_set, store_patterns, freq_data = \
=======
        self.terms, self.nlp, self.entity_ruler, self.ruler_patterns_set, store_patterns, pattern_hits = \
>>>>>>> 7e02c94140209fda44771da089b78511cbc06578
            extract_top_terms(text, self.nlp, self.entity_ruler,
                            ruler_patterns_set=self.ruler_patterns_set,
                            stopwords=self.stopwords, 
                            plural_to_singular=self.plural_to_singular,
                            patterns=patterns)
        print('Top terms extracted successfully!')

<<<<<<< HEAD
        return self.terms, store_patterns, freq_data
=======
        return self.terms, store_patterns, pattern_hits
>>>>>>> 7e02c94140209fda44771da089b78511cbc06578

    def extract_heading_terms(self, text):
        """
        extracts terms from header
        if terms were not extracted beforehand, all non-stopwords will be returned
        args:
            header: string
        returns:
            list of unique terms
        """
        doc = self.nlp(text)

        result = []

        if self.terms is None:
            # Remove duplicates
            for token in doc:
                term = token.text.lower()
                if term not in self.stopwords:
                    result.append(term)
        else:
            term_set = set(self.terms)
            for token in doc:
                term = token.ent_id_ if token.ent_id_ != '' else token.lemma_
                if term in term_set:
                    result.append(term)

        return list(set(result))

if __name__ == '__main__':
    """
    Test parser
    """
    with open('../samples/sample.txt', 'r', encoding='utf-8') as f:
        text = f.read()

    parser = Parser()

    # print(common_words)
    # print(plural_to_singular)
    print(parser.extract_terms(text))