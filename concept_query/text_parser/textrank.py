import itertools
import networkx as nx
import numpy as np
import inflection
import string
import time

import spacy
from spacy.matcher import Matcher
from spacy.pipeline import EntityRuler

def capitalize_word(text):
    return text[0:1].upper() + text[1:]

def get_variants(ent_id):
    """
    Given an entity id get capitalized and plural variants
    """

    tokens = ent_id.split('-')
    capitalized_tokens = [capitalize_word(word) for word in tokens]

    variants = set([])
    variants.add(' '.join(tokens))
    variants.add(' '.join(capitalized_tokens))
    variants.add(' '.join(tokens[:-1] + [inflection.pluralize(tokens[-1]),]))
    variants.add(' '.join(capitalized_tokens[:-1] + [inflection.pluralize(capitalized_tokens[-1]),]))
    return list(variants)

def get_acroynm_candidates(nlp, doc):
    """
    Get all singular uppercase acroynms with at least two characters
    """
    matcher = Matcher(nlp.vocab)
    pattern = [{"IS_UPPER": True}]
    matcher.add("ACROYNM", None, pattern)

    matches = matcher(doc)
    acroynm_candidates = []
    acroynm_set = set([])
    for _, start, end in matches:
        span = doc[start:end]  # The matched span
        if len(span.text) > 1 and span.text not in acroynm_set:
            acroynm_candidates.append(span)
            acroynm_set.add(span.text)

    return acroynm_candidates

def get_ent_id(span, stopwords=[], plural_to_singular={}):
    """
    Convert to lowercase, remove stopwords, and singularize known nouns
    args:
        stopwords: list of stopwords
        plural_to_singular: dict of (plural, singular), used instead
            of lemma_ attribute so only known nouns are converted
    returns:
        ent_id
    """

    simplified_tokens = []
    for token in span:
        text = token.text.lower()
        if token.is_upper:
            simplified_tokens.append(text)
        elif text not in stopwords and text not in string.punctuation:
            if text in plural_to_singular.keys():
                singular = plural_to_singular[text]
            else:
                singular = text
            simplified_tokens.append(singular)

    return '-'.join(simplified_tokens)

def get_entity_patterns(nlp, doc, stopwords=[], plural_to_singular={}):
    """
    Get list of entity patterns
    entity_ids have stopwords removed and singularized
    potential acroynms are detected by matching singular acroynms with entity_ids
    variants (capitalized, pluralized) are included in the final entity patterns
    args:
        nlp: corpus
        doc: spaCy doc
        stopwords: stopwords
        plural_to_singular: dict of (plural, singular)
    returns:
        list of (label, pattern, id)
    """

    entity_rules = []
    entity_set = set([])
    entity_ids = set([])
    skiplabels = [ 'DATE','TIME', 'PERCENT', 'MONEY', 'QUANTITY','ORDINAL', 'CARDINAL']

    for ent in doc.ents:
        ent_id = get_ent_id(ent, stopwords, plural_to_singular)
        # Ent id can't be empty string
        if ent_id == '':
            continue

        # Remove literal duplicates
        if ent.label_ not in skiplabels and ent.text not in entity_set:
            entity_rules.append((ent, ent_id))
            entity_set.add(ent.text)
            entity_ids.add(ent_id)

    ent_id_list = list(entity_ids)

    # Find acroynms
    acroynm_candidates = get_acroynm_candidates(nlp, doc)
    # Find (acroynm, meaning) pairs
    acronym_pairs = {}
    acronym_rules = []

    for cand in acroynm_candidates:
        cand_lower = cand.text.lower()

        for ent_id in ent_id_list:
            tokens = ent_id.split('-')
            
            if len(cand_lower) == len(tokens):
                try:
                    match = all([cand_lower[i] == tokens[i][0] for i in range(len(cand_lower))])
                except IndexError:
                    match = False
            else:
                match = False
            
            if match:
                acronym_pairs[cand_lower] = ent_id
                acronym_pairs[cand_lower + 's'] = ent_id
                
                # Add singular and plural rules to entity patterns
                acronym_rules.append((cand.text, ent_id))
                acronym_rules.append((cand.text + 's', ent_id))
                break

    entity_patterns = []
    pattern_set = set([])

    # Original patterns
    for span, ent_id in entity_rules:
        # Strip leading "the"
        pattern = span[1:].text if span[0].text in ['the', 'The'] else span.text
        # Handle abbreviations
        pattern_id = acronym_pairs[ent_id] if ent_id in acronym_pairs.keys() else ent_id
        entity_patterns.append({'label':'CUSTOM', 'pattern':pattern, 'id':pattern_id})
        # Add to set to remove duplicate literal acroynm patterns
        pattern_set.add(pattern)

    # # Variant patterns
    # for ent_id in ent_id_list:
    #     for variant in get_variants(ent_id):
    #         if variant not in pattern_set:
    #             entity_patterns.append({'label':'CUSTOM', 'pattern':variant, 'id':ent_id})
    #             pattern_set.add(variant)

    for pattern, ent_id in acronym_rules:
        if pattern not in pattern_set:
            entity_patterns.append({'label':'CUSTOM', 'pattern':pattern, 'id':ent_id})

    return entity_patterns

def get_keywords(doc):
    unique_word_set = set([])
    edges = {}

    for sent in doc.sents:
        word_list = []
        word_set = set([])
        for w in sent:
            if w.pos_ in ['ADJ', 'ADV', 'NOUN', 'PROPN', 'X'] and w.text not in word_set:
                word_list.append(w.text)
                word_set.add(w.text)

        unique_word_set.update(word_set)

        for pair in itertools.combinations(word_list, 2):
            if pair in edges.keys():
                edges[pair] += 1
            else:
                edges[pair] = 1

    gr = nx.DiGraph()  # initialize an undirected graph
    gr.add_nodes_from(unique_word_set)

    for key, weight in edges.items():
        gr.add_edge(key[0], key[1], weight=weight)
    
    calculated_page_rank = nx.pagerank(gr, weight='weight')
    sorted_keywords = sorted(calculated_page_rank, key=calculated_page_rank.get,reverse=True)
    return sorted_keywords

def get_top_phrases(doc, keywords, k=2):
    """
    Finds valid phrases (groups of consecutive keywords) of length k
    args:
        textlist: tokenized list of words
        keywords: valid keywords
        k: phrase length
    returns:
        list of tuples
        phrase freq: (phrase tuple, freq)
        keyword freq: (keyword, freq)
    """
    phrase_set = set([])
    phrase_freq = {}
    keyword_freq = {}

    i = k-1
    while i < len(doc):
        consecutive = tuple([token.text for token in doc[i-k+1:i+1]])
        if all([word in keywords for word in consecutive]):
            phrase_set.add(consecutive)
            if consecutive in phrase_freq.keys():
                phrase_freq[consecutive] += 1
            else:
                phrase_freq[consecutive] = 1
        i += 1
        
    keyword_freq = {}
    for token in doc:
        if token.text in keywords:
            if token.text in keyword_freq.keys():
                keyword_freq[token.text] += 1
            else:
                keyword_freq[token.text] = 1

    # Get phrase scores
    phrase_scores = {}
    for p in list(phrase_set):
        score = np.prod([phrase_freq[p] / keyword_freq[w] for w in p])
        # Normalize score
        phrase_scores[p] = np.power(score, 1/len(p))
    
    sorted_phrases = sorted(phrase_scores, key=phrase_scores.get,reverse=True)
    # print(sorted_phrases)
    return sorted_phrases[:len(sorted_phrases)//3]

def get_phrase_patterns(doc, plural_to_singular={}):
    keywords = get_keywords(doc)
    # print('textrank:230>', keywords)
    bigrams = get_top_phrases(doc, keywords[:len(keywords)//10], k=2)
    # print('textrank:232>', bigrams)

    entity_patterns = []
    for phrase in bigrams:
        pattern_id = '-'.join(phrase).lower()
        # for variant in get_variants(pattern_id):
        entity_patterns.append({'label':'CUSTOM', 'pattern':' '.join(phrase), 'id':pattern_id})

    return entity_patterns

def new_deduplicated_variants(patterns, ruler_patterns_set, stopwords):
    new_patterns = []
    ent_id_set = set([])

    for pat in patterns:
        if pat['pattern'] not in ruler_patterns_set:
            new_patterns.append(pat)
        ruler_patterns_set.add(pat['pattern'])

        if pat['id'] not in ent_id_set and pat['id'] not in stopwords:
            for variant in get_variants(pat['id']):
                if variant not in ruler_patterns_set:
                    new_patterns.append({'label':'CUSTOM', 'pattern':variant, 'id':pat['id']})
                ruler_patterns_set.add(variant)
        ent_id_set.add(pat['id'])

    return new_patterns

def extract_top_terms(text, nlp, ruler, ruler_patterns_set,
        stopwords=[], plural_to_singular={}, patterns=[]):
    """
    Finds the top terms. This can be either single words or bigrams.
    args:
        text: string
        nlp: spacy nlp
        ruler: entity_ruler
        ruler_patterns_set: patterns in ruler for easy checking
        stopwords: list of stopwords
        plural_to_singular: dict of (plural, singular) items
        patterns: list of new patterns (from database)
    returns:
        list of strings

    ref:
        https://spacy.io/usage/rule-based-matching#entityruler
    """
    start = time.time()
    doc = nlp(text)
    print('textrank:278>', time.time() - start)

    entity_patterns = get_entity_patterns(nlp, doc, stopwords, plural_to_singular)
    phrase_patterns = get_phrase_patterns(doc, plural_to_singular)
    all_patterns = patterns + entity_patterns + phrase_patterns
    # Get new patterns to add to pipe
    # print('textrank:288>', len(list(ruler_patterns_set)))
    new_patterns = new_deduplicated_variants(all_patterns, ruler_patterns_set, stopwords)
    # print('textrank:290>', len(new_patterns), len(list(ruler_patterns_set)))
    print('textrank:287>', time.time() - start)

    # ruler = EntityRuler(nlp)
    other_pipes = [p for p in nlp.pipe_names if p != "tagger"]
    with nlp.disable_pipes(*other_pipes):
        ruler.add_patterns(new_patterns)

    nlp.replace_pipe('entity_ruler', ruler)
    print('textrank:295>', time.time() - start)

    pattern_hits = set([])
    freq_data = {} # (pattern, freq) key-value pairs
    # Retokenize entities
    modified_doc = nlp(text)
    with modified_doc.retokenize() as retokenizer:
        for ent in modified_doc.ents:
            retokenizer.merge(ent)
            pattern_hits.add(ent.text)

            pair = (ent.ent_id_, ent.text)
            if pair in freq_data.keys():
                freq_data[pair] += 1
            else:
                freq_data[pair] = 1

    print('textrank:302>', time.time() - start)

    # Compile new patterns to add to DB
    old_patterns_set = set([p['pattern'] for p in patterns])
    store_patterns = []
    for pat in new_patterns:
        if pat['pattern'] in pattern_hits and pat['pattern'] not in old_patterns_set:
            store_patterns.append(pat)
    print('textrank:310>', time.time() - start)

    unique_term_set = set([])
    edges = {}

    for s in modified_doc.sents:
    #     unique_nouns = set([])
        noun_list = []
        for token in s:
            if token.pos_ in ['NOUN', 'PROPN', 'X'] and len(token.text) > 1:
                if token.ent_id_ != '':
                    noun = token.ent_id_
                else:
                    noun = token.lemma_
    #             print(token.lemma_)
                noun = noun.replace('"', "'")
                if noun not in noun_list:
                    noun_list.append(noun)
        # print(noun_list)
        
        unique_term_set.update(noun_list)

        for pair in itertools.combinations(noun_list, 2):
            if pair in edges.keys():
                edges[pair] += 1
            else:
                edges[pair] = 1

    gr = nx.DiGraph()  # initialize an undirected graph
    gr.add_nodes_from(unique_term_set)

    for key, weight in edges.items():
        gr.add_edge(key[0], key[1], weight=weight)

    calculated_page_rank = nx.pagerank(gr, weight='weight')
    sorted_terms = sorted(calculated_page_rank, key=calculated_page_rank.get,reverse=True)
    print('textrank:346>', time.time() - start)
    print('text_rank:347>', len(store_patterns))

    # print(freq_data)
    # for pat in store_patterns:
    #     assert (pat['id'], pat['pattern']) in freq_data.keys(), \
    #         f"{pat['id']}, {pat['pattern']}"

    return sorted_terms[:len(sorted_terms) // 3], nlp, ruler, \
        ruler_patterns_set, store_patterns, freq_data
    